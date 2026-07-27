"""Governed execution and family-level runtime-invariant conformance."""

from __future__ import annotations

import gc
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .backends import (
    BackendError,
    DeterministicFixtureBackend,
    InferenceBackend,
    LlamaCppBackend,
)
from .contracts import RuntimeContract, load_contract, validate_input, validate_output
from .manifest import ROOT, FamilyManifest, TierSpec, load_manifest
from .proof import (
    atomic_write_json,
    current_git_commit,
    seal_record,
    sha256_value,
    utc_now,
)
from .weights import inspect_tier

BackendFactory = Callable[[TierSpec], InferenceBackend]
DEFAULT_ARTIFACTS_DIR = ROOT / "artifacts"
DEFAULT_WEIGHTS_DIR = ROOT / "weights"
INVARIANT_KEYS = (
    "contract_hash",
    "contract_version",
    "family",
    "governance_order",
    "response_schema",
)


def _base_record(
    *,
    spec: TierSpec,
    manifest: FamilyManifest,
    contract: RuntimeContract,
    prompt: object,
) -> dict[str, Any]:
    prompt_evidence: object
    if isinstance(prompt, str):
        prompt_evidence = prompt
    else:
        prompt_type = type(prompt)
        prompt_evidence = {
            "invalid_input_type": f"{prompt_type.__module__}.{prompt_type.__qualname__}"
        }
    return {
        "@context": "https://oims.collective-osp.org/conformance/v2",
        "@type": "OIMSModelTierConformanceRecord",
        "schema_version": 2,
        "created_at": utc_now(),
        "family": manifest.family,
        "model": spec.name,
        "parameter_class": spec.parameter_class,
        "prompt_sha256": sha256_value(prompt_evidence),
        "contract_version": contract.version,
        "contract_hash": contract.source_hash,
        "weight_source": {
            "repo_id": spec.repo_id,
            "revision": spec.revision,
            "quantization": spec.quantization,
            "license": spec.license,
            "files": list(spec.files),
        },
        "source_commit": current_git_commit(ROOT),
    }


def _invariant_vector(
    manifest: FamilyManifest,
    contract: RuntimeContract,
) -> dict[str, str]:
    return {
        "contract_hash": contract.source_hash,
        "contract_version": contract.version,
        "family": manifest.family,
        "governance_order": "preflight->inference->output-validation->receipt",
        "response_schema": "OIMSModelTierConformanceRecord/v2",
    }


def _write_tier_artifact(
    record: dict[str, Any],
    artifacts_dir: Path,
) -> dict[str, Any]:
    sealed = seal_record(record)
    atomic_write_json(artifacts_dir / f"{record['model'].lower()}-conformance.jsonld", sealed)
    return sealed


def run_tier(
    tier: str,
    prompt: object,
    *,
    manifest: FamilyManifest | None = None,
    contract: RuntimeContract | None = None,
    backend_factory: BackendFactory | None = None,
    weights_dir: Path = DEFAULT_WEIGHTS_DIR,
    artifacts_dir: Path = DEFAULT_ARTIFACTS_DIR,
    max_tokens: int = 256,
) -> dict[str, Any]:
    manifest = manifest or load_manifest()
    contract = contract or load_contract(ROOT / manifest.shared_contract)
    spec = manifest.tier(tier)
    record = _base_record(
        spec=spec,
        manifest=manifest,
        contract=contract,
        prompt=prompt,
    )
    input_decision = validate_input(prompt, contract)
    record["preflight"] = {
        "status": input_decision.status,
        "code": input_decision.code,
        "lawful": input_decision.lawful,
    }
    record["invariant_vector"] = _invariant_vector(manifest, contract)

    if not input_decision.should_execute:
        record.update(
            {
                "status": input_decision.status,
                "lawful": input_decision.lawful,
                "weight_execution_verified": False,
                "runtime_drift": 0.0 if input_decision.lawful else 1.0,
                "output": input_decision.message,
                "backend": {"name": "not-executed", "real_weights": False},
            }
        )
        return _write_tier_artifact(record, artifacts_dir)

    factory = backend_factory or (
        lambda selected: LlamaCppBackend(selected, weights_root=weights_dir)
    )
    backend: InferenceBackend | None = None
    try:
        backend = factory(spec)
        result = backend.generate(str(prompt), max_tokens=max_tokens)
        output_decision = validate_output(result.output, contract)
        weight_status = inspect_tier(spec, weights_dir, compute_hashes=False)
        if result.metadata.get("weight_hash_verified", False):
            weight_status["hash_verified"] = True
            weight_status["verification"] = "sha256-revalidated-before-load"
        record.update(
            {
                "status": output_decision.status,
                "lawful": output_decision.lawful,
                "weight_execution_verified": bool(
                    result.real_weights and result.metadata.get("weight_hash_verified", False)
                ),
                "runtime_drift": 0.0 if output_decision.lawful else 1.0,
                "output": result.output if output_decision.lawful else output_decision.message,
                "output_sha256": sha256_value(result.output),
                "backend": {
                    "name": result.backend,
                    "real_weights": result.real_weights,
                    "elapsed_ms": result.elapsed_ms,
                    "metadata": result.metadata,
                },
                "weight_inventory": weight_status,
            }
        )
    except BackendError as exc:
        record.update(
            {
                "status": "BACKEND_UNAVAILABLE",
                "lawful": False,
                "weight_execution_verified": False,
                "runtime_drift": 1.0,
                "output": str(exc),
                "backend": {"name": "unavailable", "real_weights": False},
            }
        )
    finally:
        if backend is not None:
            try:
                backend.close()
            except (RuntimeError, OSError) as exc:
                record["backend_cleanup_warning"] = str(exc)
        del backend
        gc.collect()

    return _write_tier_artifact(record, artifacts_dir)


def _runtime_drift(records: list[dict[str, Any]]) -> float:
    if not records:
        return 1.0
    baseline = records[0].get("invariant_vector", {})
    comparisons = 0
    mismatches = 0
    for record in records[1:]:
        candidate = record.get("invariant_vector", {})
        for key in INVARIANT_KEYS:
            comparisons += 1
            if baseline.get(key) != candidate.get(key):
                mismatches += 1
    return 0.0 if comparisons == 0 else mismatches / comparisons


def run_family(
    prompt: object,
    *,
    manifest: FamilyManifest | None = None,
    contract: RuntimeContract | None = None,
    backend_factory: BackendFactory | None = None,
    weights_dir: Path = DEFAULT_WEIGHTS_DIR,
    artifacts_dir: Path = DEFAULT_ARTIFACTS_DIR,
    max_tokens: int = 256,
) -> dict[str, Any]:
    manifest = manifest or load_manifest()
    contract = contract or load_contract(ROOT / manifest.shared_contract)
    records = [
        run_tier(
            spec.name,
            prompt,
            manifest=manifest,
            contract=contract,
            backend_factory=backend_factory,
            weights_dir=weights_dir,
            artifacts_dir=artifacts_dir,
            max_tokens=max_tokens,
        )
        for spec in manifest.tiers
    ]
    drift = _runtime_drift(records)
    lawful = all(record["status"] == "LAWFUL" for record in records)
    weight_backed = all(record["weight_execution_verified"] for record in records)
    report = {
        "@context": "https://oims.collective-osp.org/conformance/v2",
        "@type": "OIMSFamilyConformanceReport",
        "schema_version": 2,
        "created_at": utc_now(),
        "family": manifest.family,
        "executed_tiers": [record["model"] for record in records],
        "status": "CONFORMANT"
        if lawful and drift <= contract.max_runtime_drift
        else "NONCONFORMANT",
        "runtime_isomorphic": lawful and drift <= contract.max_runtime_drift,
        "weight_execution_verified": weight_backed,
        "evidence_class": "WEIGHT_BACKED" if weight_backed else "TEST_OR_INCOMPLETE",
        "runtime_drift": drift,
        "max_runtime_drift": contract.max_runtime_drift,
        "contract_hash": contract.source_hash,
        "tier_record_hashes": {record["model"]: record["record_sha256"] for record in records},
        "results": records,
        "source_commit": current_git_commit(ROOT),
    }
    sealed = seal_record(report)
    atomic_write_json(artifacts_dir / "conformance_report.jsonld", sealed)
    return sealed


def fixture_backend_factory(spec: TierSpec) -> InferenceBackend:
    return DeterministicFixtureBackend(spec)


def print_json(value: dict[str, Any]) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True))
