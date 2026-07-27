"""Fail-closed verification for OIMS tier, family, and CollectiveOS receipts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .agents import AgentRegistry, load_agent_registry
from .contracts import RuntimeContract, load_contract
from .manifest import ROOT, FamilyManifest, load_manifest
from .proof import verify_sealed_record


def _verify_tier(
    record: dict[str, Any],
    *,
    manifest: FamilyManifest,
    contract: RuntimeContract,
) -> list[str]:
    errors: list[str] = []
    if not verify_sealed_record(record):
        errors.append("tier record seal is invalid")
    try:
        spec = manifest.tier(str(record.get("model")))
    except ValueError as exc:
        return [str(exc)]
    expected = {
        "family": manifest.family,
        "parameter_class": spec.parameter_class,
        "capacity_class": spec.capacity_class,
        "provider": spec.provider,
        "architecture_family": spec.architecture_family,
        "contract_hash": contract.source_hash,
        "contract_version": contract.version,
    }
    for field, value in expected.items():
        if record.get(field) != value:
            errors.append(f"tier field {field} does not match the active manifest/contract")
    source = record.get("weight_source")
    if not isinstance(source, dict):
        errors.append("tier weight_source is missing")
    else:
        source_expected = {
            "repo_id": spec.repo_id,
            "base_model_repo_id": spec.base_model_repo_id,
            "revision": spec.revision,
            "quantization": spec.quantization,
            "license": spec.license,
            "conversion": spec.conversion,
            "files": [item.to_mapping() for item in spec.weight_files],
        }
        if source != source_expected:
            errors.append("tier weight_source does not match the pinned manifest")
    binding = record.get("agent_binding")
    if binding is not None and (not isinstance(binding, dict) or binding.get("tier") != spec.name):
        errors.append("tier agent_binding is invalid")
    source_commit = record.get("source_commit")
    if not isinstance(source_commit, str) or len(source_commit) != 40:
        errors.append("tier source_commit is missing or invalid")
    if record.get("weight_execution_verified") is True:
        backend = record.get("backend", {})
        metadata = backend.get("metadata", {}) if isinstance(backend, dict) else {}
        if not (
            backend.get("real_weights") is True
            and metadata.get("weight_hash_verified") is True
            and metadata.get("upstream_identity_verified") is True
        ):
            errors.append("weight-backed claim lacks backend identity evidence")
        inventory = record.get("weight_inventory")
        if not isinstance(inventory, dict):
            errors.append("weight-backed claim lacks verified weight inventory")
        else:
            expected_files = {item.filename: item.to_mapping() for item in spec.weight_files}
            observed_files = {
                item.get("filename"): item
                for item in inventory.get("files", [])
                if isinstance(item, dict)
            }
            identities_match = (
                inventory.get("hash_verified") is True
                and inventory.get("lock_matches_manifest") is True
                and set(observed_files) == set(expected_files)
                and all(
                    observed_files[name].get("size") == expected["size"]
                    and observed_files[name].get("sha256") == expected["sha256"]
                    for name, expected in expected_files.items()
                )
            )
            if not identities_match:
                errors.append("weight inventory does not match pinned manifest identities")
            if metadata.get("verified_weight_inventory") != inventory:
                errors.append("backend and tier weight inventories are inconsistent")
    return errors


def _verify_family(
    record: dict[str, Any],
    *,
    manifest: FamilyManifest,
    contract: RuntimeContract,
) -> list[str]:
    errors: list[str] = []
    if not verify_sealed_record(record):
        errors.append("family record seal is invalid")
    expected_tiers = [tier.name for tier in manifest.tiers]
    expected_architectures = [tier.architecture_family for tier in manifest.tiers]
    expected_providers = [tier.provider for tier in manifest.tiers]
    if record.get("family") != manifest.family:
        errors.append("family identity does not match manifest")
    if record.get("contract_hash") != contract.source_hash:
        errors.append("family contract hash does not match active contract")
    if record.get("executed_tiers") != expected_tiers:
        errors.append("family did not execute every manifest tier in declared order")
    if record.get("executed_architectures") != expected_architectures:
        errors.append("family architecture evidence does not match manifest")
    if record.get("executed_providers") != expected_providers:
        errors.append("family provider evidence does not match manifest")
    if record.get("mesh") != manifest.mesh.to_mapping():
        errors.append("family mesh declaration does not match manifest")
    if record.get("heterogeneous_architectures_verified") is not True:
        errors.append("heterogeneous architecture verification is not true")

    results = record.get("results")
    if not isinstance(results, list) or len(results) != len(manifest.tiers):
        errors.append("family results are incomplete")
        return errors
    hashes = record.get("tier_record_hashes")
    if not isinstance(hashes, dict):
        errors.append("family tier_record_hashes are missing")
        hashes = {}
    for result in results:
        if not isinstance(result, dict):
            errors.append("family result is not an object")
            continue
        errors.extend(_verify_tier(result, manifest=manifest, contract=contract))
        if hashes.get(result.get("model")) != result.get("record_sha256"):
            errors.append(f"tier hash link is invalid for {result.get('model')}")

    invariant_keys = (
        "contract_hash",
        "contract_version",
        "family",
        "governance_order",
        "response_schema",
    )
    baseline = results[0].get("invariant_vector", {})
    comparisons = 0
    mismatches = 0
    for result in results[1:]:
        candidate = result.get("invariant_vector", {})
        for key in invariant_keys:
            comparisons += 1
            if baseline.get(key) != candidate.get(key):
                mismatches += 1
    expected_drift = 0.0 if comparisons == 0 else mismatches / comparisons
    if record.get("runtime_drift") != expected_drift:
        errors.append("family runtime_drift does not match tier invariant vectors")
    if record.get("max_runtime_drift") != contract.max_runtime_drift:
        errors.append("family max_runtime_drift does not match active contract")
    lawful = all(result.get("status") == "LAWFUL" for result in results)
    diverse = len(set(expected_architectures)) == len(expected_architectures) and len(
        set(expected_providers)
    ) == len(expected_providers)
    expected_conformance = lawful and expected_drift <= contract.max_runtime_drift and diverse
    if record.get("runtime_isomorphic") is not expected_conformance:
        errors.append("family runtime_isomorphic decision is inconsistent with evidence")
    expected_status = "CONFORMANT" if expected_conformance else "NONCONFORMANT"
    if record.get("status") != expected_status:
        errors.append("family status is inconsistent with evidence")
    source_commit = record.get("source_commit")
    if not isinstance(source_commit, str) or len(source_commit) != 40:
        errors.append("family source_commit is missing or invalid")
    elif any(result.get("source_commit") != source_commit for result in results):
        errors.append("tier source commits do not match family source commit")

    all_weight_backed = all(result.get("weight_execution_verified") is True for result in results)
    if record.get("weight_execution_verified") is not all_weight_backed:
        errors.append("family weight_execution_verified is inconsistent with tier evidence")
    expected_class = "WEIGHT_BACKED" if all_weight_backed else "TEST_OR_INCOMPLETE"
    if record.get("evidence_class") != expected_class:
        errors.append("family evidence_class is inconsistent with tier evidence")
    return errors


def _verify_collective(
    record: dict[str, Any],
    *,
    manifest: FamilyManifest,
    contract: RuntimeContract,
    registry: AgentRegistry,
) -> list[str]:
    errors: list[str] = []
    if not verify_sealed_record(record):
        errors.append("CollectiveOS response seal is invalid")
    if record.get("activation_semantics") != "role_binding_only":
        errors.append("CollectiveOS activation semantics are invalid")
    if record.get("autonomous_worker_claim") is not False:
        errors.append("CollectiveOS response contains an autonomous worker claim")
    if record.get("governance_route") != list(registry.governance_route):
        errors.append("CollectiveOS governance route is invalid")
    result = record.get("result")
    if not isinstance(result, dict):
        return errors + ["CollectiveOS result record is missing"]
    errors.extend(_verify_tier(result, manifest=manifest, contract=contract))
    if record.get("result_record_sha256") != result.get("record_sha256"):
        errors.append("CollectiveOS result hash link is invalid")
    binding = record.get("agent_binding")
    if not isinstance(binding, dict):
        errors.append("CollectiveOS agent binding is missing")
    else:
        try:
            profile = registry.resolve(str(binding.get("id")))
        except ValueError as exc:
            errors.append(str(exc))
        else:
            expected_binding = registry.binding(profile)
            if binding != expected_binding or result.get("agent_binding") != binding:
                errors.append("CollectiveOS agent binding does not match registry/result")
    if record.get("agent_manifest_sha256") != registry.source_hash:
        errors.append("CollectiveOS agent manifest hash does not match active registry")
    return errors


def verify_artifact(
    value: dict[str, Any],
    *,
    manifest: FamilyManifest | None = None,
    contract: RuntimeContract | None = None,
    registry: AgentRegistry | None = None,
) -> dict[str, Any]:
    manifest = manifest or load_manifest()
    contract = contract or load_contract(ROOT / manifest.shared_contract)
    registry = registry or load_agent_registry(manifest=manifest)
    record_type = value.get("@type")
    if record_type == "OIMSModelTierConformanceRecord":
        errors = _verify_tier(value, manifest=manifest, contract=contract)
    elif record_type == "OIMSFamilyConformanceReport":
        errors = _verify_family(value, manifest=manifest, contract=contract)
    elif record_type == "CollectiveOIMSResponse":
        errors = _verify_collective(
            value,
            manifest=manifest,
            contract=contract,
            registry=registry,
        )
    else:
        errors = [f"unsupported artifact type: {record_type!r}"]
    return {
        "valid": not errors,
        "artifact_type": record_type,
        "record_sha256": value.get("record_sha256"),
        "evidence_class": value.get("evidence_class"),
        "errors": errors,
    }


def verify_artifact_file(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "valid": False,
            "artifact_type": None,
            "record_sha256": None,
            "evidence_class": None,
            "errors": [f"cannot load artifact {path}: {exc}"],
        }
    if not isinstance(value, dict):
        return {
            "valid": False,
            "artifact_type": None,
            "record_sha256": None,
            "evidence_class": None,
            "errors": ["artifact root must be a JSON object"],
        }
    return verify_artifact(value)
