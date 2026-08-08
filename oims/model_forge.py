"""Fail-closed virtual training environment for governed model modification.

The Model Forge has two executable modes in this release:

``simulate``
    Exercise plan validation, resource accounting, telemetry, checkpoint chaining, rollback
    metadata, and receipt verification without loading or modifying a model.

``probe``
    Inspect an offline OCI sandbox and one NVIDIA device.  This mode never loads weights or
    starts training.  It requires an exact plan-hash acknowledgement and an explicit
    environment unlock.

Neither mode emits a QMF-admissible training run.  Physical training remains a later state
transition after byte-exact base weights, a rights-reviewed dataset, a locked training image,
and an independently approved QMF plan exist.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from datetime import datetime, timedelta
from pathlib import Path, PurePosixPath
from typing import Any

from .manifest import ROOT
from .proof import atomic_write_json, current_git_commit, seal_record, verify_sealed_record

FORGE_SCHEMA_VERSION = "1.0.0"
QMF_DERIVATION_VERSION = "10.0.0"
MAX_PLAN_BYTES = 1024 * 1024
MAX_RECORD_BYTES = 1024 * 1024
MAX_TELEMETRY_BYTES = 16 * 1024 * 1024
DEFAULT_FORGE_ARTIFACTS_DIR = ROOT / "artifacts" / "model-forge"
GPT_OSS_20B_REPOSITORY = "openai/gpt-oss-20b"
GPT_OSS_20B_REVISION = "6cee5e81ee83917806bbde320786a8fb61efebee"
QMF_DIGEST_LENGTH = 71
EXPECTED_TARGET_PARAMETERS = [
    "15.mlp.experts.down_proj",
    "15.mlp.experts.gate_up_proj",
    "23.mlp.experts.down_proj",
    "23.mlp.experts.gate_up_proj",
    "7.mlp.experts.down_proj",
    "7.mlp.experts.gate_up_proj",
]
GOVERNANCE_ROUTE = ["QC", "GATA", "GATA_PRIME"]
SIMULATION_LIMITATIONS = [
    "no weights were loaded or modified",
    "no optimizer or gradient step executed",
    "resource observations are deterministic fixtures",
    "this receipt cannot satisfy a QMF model-training-run contract",
]

TOP_LEVEL_KEYS = {
    "schema_version",
    "plan_id",
    "mode",
    "evidence_class",
    "qmf_contract",
    "target",
    "sandbox",
    "resources",
    "recipe",
    "checkpoints",
    "simulation",
    "plan_hash",
}
QMF_KEYS = {
    "schema_version",
    "training_plan_hash",
    "base_source_manifest_hash",
    "base_artifact_hash",
    "base_model_program_hash",
    "base_model_program_rule_hash",
    "dataset_manifest_hash",
    "toolchain_lock_hash",
    "recipe_hash",
    "budget_hash",
    "benchmark_suite_hash",
    "rollback_artifact_hash",
    "output_repository_id",
    "output_format",
    "evidence_only",
    "admissible",
}
TARGET_KEYS = {
    "repository_id",
    "revision",
    "local_model_path",
    "local_dataset_path",
    "local_files_only",
    "trust_remote_code",
}
SANDBOX_KEYS = {
    "runtime",
    "network_mode",
    "read_only_root",
    "drop_all_capabilities",
    "no_new_privileges",
    "seccomp_profile",
    "base_model_mount_read_only",
    "dataset_mount_read_only",
    "output_mount",
    "tmpfs_mount",
}
RESOURCE_KEYS = {
    "hardware_profile_id",
    "device_id",
    "memory_domains",
    "max_duration_seconds",
    "max_steps",
    "max_input_tokens",
    "max_output_bytes",
    "max_peak_host_bytes",
    "max_peak_device_bytes",
    "max_energy_wh",
    "max_cost_microusd",
    "max_temperature_millic",
    "allow_swap",
}
MEMORY_DOMAIN_KEYS = {"id", "kind", "capacity_bytes"}
RECIPE_KEYS = {
    "method",
    "output_format",
    "merge_adapter",
    "preserve_harmony_format",
    "dynamic_packing",
    "train_on_responses_only",
    "gradient_checkpointing",
    "seed",
    "max_length",
    "epochs_milli",
    "learning_rate_ppb",
    "per_device_batch_size",
    "gradient_accumulation_steps",
    "lora_rank",
    "lora_alpha",
    "lora_dropout_bps",
    "target_modules",
    "target_parameters",
}
CHECKPOINT_KEYS = {"interval_steps", "retain_last", "rollback_to_base", "hash_chain"}
SIMULATION_KEYS = {
    "clock_start",
    "step_duration_seconds",
    "steps",
    "input_tokens_per_step",
    "output_bytes_per_checkpoint",
    "peak_host_bytes",
    "peak_device_bytes",
    "energy_wh_per_step",
    "max_temperature_millic",
    "synthetic_loss_millionths",
}
RUN_RECEIPT_KEYS = {
    "@context",
    "@type",
    "schema_version",
    "run_id",
    "plan_id",
    "plan_hash",
    "mode",
    "status",
    "evidence_class",
    "synthetic",
    "qmf_admissible",
    "deployable_artifact",
    "authority",
    "started_at",
    "completed_at",
    "steps",
    "input_tokens",
    "output_bytes",
    "duration_seconds",
    "peak_host_bytes",
    "peak_device_bytes",
    "energy_wh",
    "cost_microusd",
    "max_temperature_millic",
    "network_mode",
    "swap_used",
    "telemetry_file",
    "telemetry_hash",
    "checkpoint_directory",
    "checkpoint_count",
    "checkpoint_chain_head",
    "candidate_file",
    "candidate_hash",
    "rollback_artifact_hash",
    "governance_route",
    "limitations",
    "source_commit",
    "record_sha256",
}
SYNTHETIC_CHECKPOINT_KEYS = {
    "schema_version",
    "run_id",
    "evidence_class",
    "synthetic",
    "step",
    "previous_checkpoint_hash",
    "plan_hash",
    "input_tokens",
    "synthetic_loss_millionths",
    "synthetic_output_bytes",
    "checkpoint_hash",
}
TELEMETRY_KEYS = {
    "schema_version",
    "run_id",
    "evidence_class",
    "synthetic",
    "step",
    "observed_at",
    "input_tokens",
    "peak_host_bytes",
    "peak_device_bytes",
    "energy_wh",
    "temperature_millic",
    "synthetic_loss_millionths",
}
CANDIDATE_KEYS = {
    "schema_version",
    "run_id",
    "evidence_class",
    "artifact_kind",
    "not_a_model",
    "not_a_peft_adapter",
    "qmf_admissible",
    "plan_hash",
    "checkpoint_chain_head",
    "candidate_hash",
}


class ForgePlanError(ValueError):
    """Raised when a Forge input cannot be loaded or safely evaluated."""


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    return value


def qmf_canonical_json(value: Any) -> str:
    """Return the byte-equivalent canonical JSON representation used by QMF v0.10."""

    return json.dumps(
        _jsonable(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


def qmf_digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(qmf_canonical_json(value).encode("utf-8")).hexdigest()


def prefixed_file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def compute_plan_hash(plan: dict[str, Any]) -> str:
    body = dict(plan)
    body.pop("plan_hash", None)
    return qmf_digest(body)


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _is_int(value: object, *, minimum: int = 0) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= minimum


def _is_digest(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == QMF_DIGEST_LENGTH
        and value.startswith("sha256:")
        and all(character in "0123456789abcdef" for character in value.removeprefix("sha256:"))
    )


def _is_revision(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 40
        and all(character in "0123456789abcdef" for character in value)
    )


def _is_repository_id(value: object) -> bool:
    if not isinstance(value, str) or value.count("/") != 1:
        return False
    owner, name = value.split("/", 1)
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")
    return bool(owner and name) and set(owner) <= allowed and set(name) <= allowed


def _is_container_path(value: object, prefix: str) -> bool:
    if not isinstance(value, str) or not value.startswith(prefix):
        return False
    path = PurePosixPath(value)
    return path.is_absolute() and ".." not in path.parts and str(path) == value


def _is_immutable_image_ref(value: object) -> bool:
    if not isinstance(value, str) or "@sha256:" not in value:
        return False
    name, digest = value.rsplit("@sha256:", 1)
    return (
        bool(name)
        and len(digest) == 64
        and all(character in "0123456789abcdef" for character in digest)
    )


def forge_container_environment_errors(
    environment: dict[str, str] | None = None,
    *,
    require_probe_unlock: bool = False,
) -> tuple[str, ...]:
    env = environment if environment is not None else dict(os.environ)
    required = {
        "OIMS_FORGE_CONTAINER": "1",
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "HF_DATASETS_OFFLINE": "1",
    }
    if require_probe_unlock:
        required["OIMS_FORGE_ENABLE_PROBE"] = "1"
    errors = [
        f"required Forge environment {name}={expected!r} is missing"
        for name, expected in required.items()
        if env.get(name) != expected
    ]
    if not _is_immutable_image_ref(env.get("OIMS_FORGE_BASE_IMAGE")):
        errors.append("OIMS_FORGE_BASE_IMAGE is not pinned by an immutable SHA-256 digest")
    if not _is_revision(env.get("OIMS_FORGE_SOURCE_COMMIT")):
        errors.append("OIMS_FORGE_SOURCE_COMMIT is not an exact lowercase Git commit")
    return tuple(errors)


def _forge_source_commit(environment: dict[str, str] | None = None) -> str | None:
    env = environment if environment is not None else dict(os.environ)
    injected = env.get("OIMS_FORGE_SOURCE_COMMIT")
    return injected if _is_revision(injected) else current_git_commit(ROOT)


def _strict_json_loads(text: str) -> object:
    def pairs_hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON field: {key}")
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        raise ValueError(f"non-finite JSON number: {value}")

    return json.loads(text, object_pairs_hook=pairs_hook, parse_constant=reject_constant)


def _parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None and parsed.utcoffset() is not None else None


def _check_keys(
    value: object,
    expected: set[str],
    path: str,
    errors: list[str],
) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        errors.append(f"{path} must be an object")
        return None
    observed = set(value)
    missing = sorted(expected - observed)
    extra = sorted(observed - expected)
    if missing:
        errors.append(f"{path} is missing fields: {', '.join(missing)}")
    if extra:
        errors.append(f"{path} has unknown fields: {', '.join(extra)}")
    return value


def _check_exact(value: object, expected: object, path: str, errors: list[str]) -> None:
    if value != expected or type(value) is not type(expected):
        errors.append(f"{path} must be {expected!r}")


def _check_positive_int(value: object, path: str, errors: list[str], *, zero: bool = False) -> None:
    minimum = 0 if zero else 1
    if not _is_int(value, minimum=minimum):
        errors.append(f"{path} must be an integer >= {minimum}")


def load_forge_plan(path: Path | str) -> dict[str, Any]:
    plan_path = Path(path)
    try:
        size = plan_path.stat().st_size
    except OSError as exc:
        raise ForgePlanError(f"cannot stat Forge plan {plan_path}: {exc}") from exc
    if size > MAX_PLAN_BYTES:
        raise ForgePlanError(f"Forge plan exceeds {MAX_PLAN_BYTES} bytes")
    try:
        raw = _strict_json_loads(plan_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise ForgePlanError(f"cannot load Forge plan {plan_path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ForgePlanError("Forge plan root must be a JSON object")
    return raw


def validate_forge_plan(plan: object) -> tuple[str, ...]:
    errors: list[str] = []
    root = _check_keys(plan, TOP_LEVEL_KEYS, "plan", errors)
    if root is None:
        return tuple(errors)

    _check_exact(root.get("schema_version"), FORGE_SCHEMA_VERSION, "schema_version", errors)
    if not isinstance(root.get("plan_id"), str) or not root["plan_id"].strip():
        errors.append("plan_id must be a non-empty string")
    mode = root.get("mode")
    if mode not in {"simulate", "probe"}:
        errors.append("mode must be 'simulate' or 'probe'")
    expected_evidence = {"simulate": "SIMULATED", "probe": "PHYSICAL_PREFLIGHT"}.get(mode)
    if root.get("evidence_class") != expected_evidence:
        errors.append("evidence_class does not match the selected mode")

    qmf = _check_keys(root.get("qmf_contract"), QMF_KEYS, "qmf_contract", errors)
    if qmf is not None:
        _check_exact(
            qmf.get("schema_version"),
            QMF_DERIVATION_VERSION,
            "qmf_contract.schema_version",
            errors,
        )
        for field in sorted(
            QMF_KEYS
            - {
                "schema_version",
                "output_repository_id",
                "output_format",
                "evidence_only",
                "admissible",
            }
        ):
            if not _is_digest(qmf.get(field)):
                errors.append(f"qmf_contract.{field} must be a canonical SHA-256 digest")
        if not _is_repository_id(qmf.get("output_repository_id")):
            errors.append("qmf_contract.output_repository_id is invalid")
        _check_exact(qmf.get("output_format"), "peft-adapter", "qmf_contract.output_format", errors)
        _check_exact(qmf.get("evidence_only"), True, "qmf_contract.evidence_only", errors)
        _check_exact(qmf.get("admissible"), False, "qmf_contract.admissible", errors)
        if qmf.get("rollback_artifact_hash") != qmf.get("base_artifact_hash"):
            errors.append("QMF rollback artifact must be the immutable base artifact")

    target = _check_keys(root.get("target"), TARGET_KEYS, "target", errors)
    if target is not None:
        _check_exact(
            target.get("repository_id"),
            GPT_OSS_20B_REPOSITORY,
            "target.repository_id",
            errors,
        )
        _check_exact(target.get("revision"), GPT_OSS_20B_REVISION, "target.revision", errors)
        if not _is_revision(target.get("revision")):
            errors.append("target.revision must be a full lowercase commit SHA")
        if not _is_container_path(target.get("local_model_path"), "/forge/inputs/base"):
            errors.append("target.local_model_path must remain under /forge/inputs/base")
        if not _is_container_path(target.get("local_dataset_path"), "/forge/inputs/dataset"):
            errors.append("target.local_dataset_path must remain under /forge/inputs/dataset")
        _check_exact(target.get("local_files_only"), True, "target.local_files_only", errors)
        _check_exact(target.get("trust_remote_code"), False, "target.trust_remote_code", errors)

    sandbox = _check_keys(root.get("sandbox"), SANDBOX_KEYS, "sandbox", errors)
    if sandbox is not None:
        for field, expected in {
            "runtime": "oci",
            "network_mode": "none",
            "read_only_root": True,
            "drop_all_capabilities": True,
            "no_new_privileges": True,
            "seccomp_profile": "runtime-default",
            "base_model_mount_read_only": True,
            "dataset_mount_read_only": True,
            "output_mount": "/forge/output",
            "tmpfs_mount": "/tmp",
        }.items():
            _check_exact(sandbox.get(field), expected, f"sandbox.{field}", errors)

    resources = _check_keys(root.get("resources"), RESOURCE_KEYS, "resources", errors)
    if resources is not None:
        if (
            not isinstance(resources.get("hardware_profile_id"), str)
            or not resources["hardware_profile_id"].strip()
        ):
            errors.append("resources.hardware_profile_id must be a non-empty string")
        _check_positive_int(resources.get("device_id"), "resources.device_id", errors, zero=True)
        for field in sorted(
            RESOURCE_KEYS - {"hardware_profile_id", "device_id", "memory_domains", "allow_swap"}
        ):
            _check_positive_int(
                resources.get(field),
                f"resources.{field}",
                errors,
                zero=field == "max_cost_microusd",
            )
        _check_exact(resources.get("allow_swap"), False, "resources.allow_swap", errors)
        domains = resources.get("memory_domains")
        capacities_by_kind: dict[str, list[int]] = {}
        if not isinstance(domains, list) or len(domains) != 2:
            errors.append("resources.memory_domains must contain one GPU and one host domain")
        else:
            identifiers: list[str] = []
            for index, item in enumerate(domains):
                domain = _check_keys(
                    item,
                    MEMORY_DOMAIN_KEYS,
                    f"resources.memory_domains[{index}]",
                    errors,
                )
                if domain is None:
                    continue
                identifier = domain.get("id")
                kind = domain.get("kind")
                if not isinstance(identifier, str) or not identifier.strip():
                    errors.append(f"resources.memory_domains[{index}].id is invalid")
                else:
                    identifiers.append(identifier)
                if kind not in {"gpu-vram", "host-ram"}:
                    errors.append(f"resources.memory_domains[{index}].kind is invalid")
                capacity = domain.get("capacity_bytes")
                _check_positive_int(
                    capacity,
                    f"resources.memory_domains[{index}].capacity_bytes",
                    errors,
                )
                if isinstance(kind, str) and _is_int(capacity, minimum=1):
                    capacities_by_kind.setdefault(kind, []).append(capacity)
            if len(identifiers) != len(set(identifiers)):
                errors.append("resources.memory_domains identifiers must be unique")
            if set(capacities_by_kind) != {"gpu-vram", "host-ram"} or any(
                len(values) != 1 for values in capacities_by_kind.values()
            ):
                errors.append("resources.memory_domains cannot aggregate or alias physical memory")
        capacities = {
            kind: values[0] for kind, values in capacities_by_kind.items() if len(values) == 1
        }
        host_limit = resources.get("max_peak_host_bytes")
        device_limit = resources.get("max_peak_device_bytes")
        if _is_int(host_limit, minimum=1) and host_limit > capacities.get("host-ram", 0):
            errors.append("resources.max_peak_host_bytes exceeds its physical memory domain")
        if _is_int(device_limit, minimum=1) and device_limit > capacities.get("gpu-vram", 0):
            errors.append("resources.max_peak_device_bytes exceeds its physical memory domain")
        temperature = resources.get("max_temperature_millic")
        if _is_int(temperature, minimum=1) and temperature > 95_000:
            errors.append("resources.max_temperature_millic exceeds the Forge safety ceiling")

    recipe = _check_keys(root.get("recipe"), RECIPE_KEYS, "recipe", errors)
    if recipe is not None:
        for field, expected in {
            "method": "lora-sft",
            "output_format": "peft-adapter",
            "merge_adapter": False,
            "preserve_harmony_format": True,
            "dynamic_packing": True,
            "train_on_responses_only": True,
            "gradient_checkpointing": True,
        }.items():
            _check_exact(recipe.get(field), expected, f"recipe.{field}", errors)
        for field in (
            "seed",
            "max_length",
            "epochs_milli",
            "learning_rate_ppb",
            "per_device_batch_size",
            "gradient_accumulation_steps",
            "lora_rank",
            "lora_alpha",
            "lora_dropout_bps",
        ):
            _check_positive_int(
                recipe.get(field),
                f"recipe.{field}",
                errors,
                zero=field in {"seed", "lora_dropout_bps"},
            )
        dropout = recipe.get("lora_dropout_bps")
        if _is_int(dropout) and dropout > 10_000:
            errors.append("recipe.lora_dropout_bps cannot exceed 10000")
        for field in ("target_modules", "target_parameters"):
            values = recipe.get(field)
            if (
                not isinstance(values, list)
                or not values
                or not all(isinstance(item, str) and item for item in values)
                or values != sorted(set(values))
            ):
                errors.append(f"recipe.{field} must be a canonical non-empty string list")
        if recipe.get("target_modules") != ["all-linear"]:
            errors.append("recipe.target_modules must preserve the reviewed all-linear binding")
        if recipe.get("target_parameters") != EXPECTED_TARGET_PARAMETERS:
            errors.append("recipe.target_parameters must preserve the reviewed GPT-OSS MoE binding")

    checkpoints = _check_keys(root.get("checkpoints"), CHECKPOINT_KEYS, "checkpoints", errors)
    if checkpoints is not None:
        _check_positive_int(checkpoints.get("interval_steps"), "checkpoints.interval_steps", errors)
        _check_positive_int(checkpoints.get("retain_last"), "checkpoints.retain_last", errors)
        _check_exact(
            checkpoints.get("rollback_to_base"), True, "checkpoints.rollback_to_base", errors
        )
        _check_exact(checkpoints.get("hash_chain"), True, "checkpoints.hash_chain", errors)

    simulation = root.get("simulation")
    if mode == "simulate":
        sim = _check_keys(simulation, SIMULATION_KEYS, "simulation", errors)
        if sim is not None:
            if _parse_timestamp(sim.get("clock_start")) is None:
                errors.append("simulation.clock_start must be timezone-aware RFC3339")
            for field in SIMULATION_KEYS - {"clock_start", "synthetic_loss_millionths"}:
                _check_positive_int(sim.get(field), f"simulation.{field}", errors)
            losses = sim.get("synthetic_loss_millionths")
            if (
                not isinstance(losses, list)
                or not losses
                or not all(_is_int(item, minimum=0) for item in losses)
            ):
                errors.append("simulation.synthetic_loss_millionths is invalid")
            elif losses != sorted(losses, reverse=True):
                errors.append("simulation synthetic loss must be monotonic for the fixture")
            if isinstance(losses, list) and sim.get("steps") != len(losses):
                errors.append("simulation step count does not match synthetic loss observations")
            if isinstance(resources, dict):
                comparisons = {
                    "steps": "max_steps",
                    "peak_host_bytes": "max_peak_host_bytes",
                    "peak_device_bytes": "max_peak_device_bytes",
                    "max_temperature_millic": "max_temperature_millic",
                }
                for observed, ceiling in comparisons.items():
                    if (
                        _is_int(sim.get(observed))
                        and _is_int(resources.get(ceiling))
                        and sim[observed] > resources[ceiling]
                    ):
                        errors.append(f"simulation.{observed} exceeds resources.{ceiling}")
                if _is_int(sim.get("steps")) and _is_int(sim.get("input_tokens_per_step")):
                    tokens = sim["steps"] * sim["input_tokens_per_step"]
                    if (
                        _is_int(resources.get("max_input_tokens"))
                        and tokens > resources["max_input_tokens"]
                    ):
                        errors.append("simulation input tokens exceed the resource budget")
                if _is_int(sim.get("steps")) and _is_int(sim.get("energy_wh_per_step")):
                    energy = sim["steps"] * sim["energy_wh_per_step"]
                    if (
                        _is_int(resources.get("max_energy_wh"))
                        and energy > resources["max_energy_wh"]
                    ):
                        errors.append("simulation energy exceeds the resource budget")
                if _is_int(sim.get("steps")) and _is_int(sim.get("step_duration_seconds")):
                    duration = sim["steps"] * sim["step_duration_seconds"]
                    if (
                        _is_int(resources.get("max_duration_seconds"))
                        and duration > resources["max_duration_seconds"]
                    ):
                        errors.append("simulation duration exceeds the resource budget")
                if _is_int(sim.get("steps")) and _is_int(sim.get("output_bytes_per_checkpoint")):
                    output_bytes = sim["steps"] * sim["output_bytes_per_checkpoint"]
                    if (
                        _is_int(resources.get("max_output_bytes"))
                        and output_bytes > resources["max_output_bytes"]
                    ):
                        errors.append("simulation output bytes exceed the resource budget")
            if isinstance(checkpoints, dict):
                if checkpoints.get("interval_steps") != 1:
                    errors.append("simulation checkpoints.interval_steps must be 1")
                if _is_int(sim.get("steps")) and (
                    not _is_int(checkpoints.get("retain_last"))
                    or checkpoints["retain_last"] < sim["steps"]
                ):
                    errors.append("simulation checkpoints.retain_last must preserve the full chain")
    elif simulation is not None:
        errors.append("simulation must be null for physical preflight mode")

    plan_hash = root.get("plan_hash")
    if not _is_digest(plan_hash):
        errors.append("plan_hash must be a canonical SHA-256 digest")
    else:
        try:
            expected_hash = compute_plan_hash(root)
        except (TypeError, ValueError):
            errors.append("plan cannot be canonically hashed")
        else:
            if plan_hash != expected_hash:
                errors.append("plan_hash does not match the canonical plan body")
    return tuple(errors)


def forge_plan_decision(plan: object) -> dict[str, Any]:
    errors = validate_forge_plan(plan)
    plan_hash = plan.get("plan_hash") if isinstance(plan, dict) else None
    mode = plan.get("mode") if isinstance(plan, dict) else None
    record = {
        "@context": "https://oims.collective-osp.org/model-forge/v1",
        "@type": "OIMSModelForgePlanDecision",
        "schema_version": FORGE_SCHEMA_VERSION,
        "status": "ACCEPTED" if not errors else "REFUSED",
        "lawful": not errors,
        "should_execute": not errors,
        "mode": mode,
        "plan_hash": plan_hash if _is_digest(plan_hash) else None,
        "evidence_class": plan.get("evidence_class") if isinstance(plan, dict) else None,
        "qmf_admissible": False,
        "governance_route": GOVERNANCE_ROUTE,
        "errors": list(errors),
        "source_commit": _forge_source_commit(),
    }
    return seal_record(record)


def _safe_run_directory(root: Path, run_id: str) -> Path:
    resolved_root = root.resolve()
    run_dir = (resolved_root / run_id).resolve()
    if run_dir.parent != resolved_root:
        raise ForgePlanError("run identifier escaped the Forge artifacts root")
    if run_dir.exists():
        raise ForgePlanError(f"Forge run already exists: {run_dir}")
    return run_dir


def simulate_forge_run(
    plan: dict[str, Any],
    *,
    artifacts_dir: Path = DEFAULT_FORGE_ARTIFACTS_DIR,
) -> dict[str, Any]:
    errors = validate_forge_plan(plan)
    if errors:
        raise ForgePlanError("; ".join(errors))
    if plan["mode"] != "simulate":
        raise ForgePlanError("only a simulate plan can enter the simulation lane")

    plan_hash = plan["plan_hash"]
    run_id = f"sim-{plan_hash.removeprefix('sha256:')[:16]}"
    run_dir = _safe_run_directory(artifacts_dir, run_id)
    checkpoint_dir = run_dir / "checkpoints"
    candidate_dir = run_dir / "candidate"
    checkpoint_dir.mkdir(parents=True)
    candidate_dir.mkdir(parents=True)
    atomic_write_json(run_dir / "plan.json", plan)

    simulation = plan["simulation"]
    started = _parse_timestamp(simulation["clock_start"])
    if started is None:  # guarded by validation; keeps type checkers and callers honest
        raise ForgePlanError("simulation clock is invalid")
    step_duration = simulation["step_duration_seconds"]
    telemetry: list[dict[str, Any]] = []
    checkpoint_hashes: list[str] = []
    previous: str | None = None
    for step, synthetic_loss in enumerate(simulation["synthetic_loss_millionths"], start=1):
        observed_at = started + timedelta(seconds=step * step_duration)
        checkpoint_body = {
            "schema_version": FORGE_SCHEMA_VERSION,
            "run_id": run_id,
            "evidence_class": "SIMULATED",
            "synthetic": True,
            "step": step,
            "previous_checkpoint_hash": previous,
            "plan_hash": plan_hash,
            "input_tokens": step * simulation["input_tokens_per_step"],
            "synthetic_loss_millionths": synthetic_loss,
            "synthetic_output_bytes": simulation["output_bytes_per_checkpoint"],
        }
        checkpoint = dict(checkpoint_body)
        checkpoint["checkpoint_hash"] = qmf_digest(checkpoint_body)
        checkpoint_path = checkpoint_dir / f"step-{step:06d}.json"
        atomic_write_json(checkpoint_path, checkpoint)
        previous = checkpoint["checkpoint_hash"]
        checkpoint_hashes.append(previous)
        telemetry.append(
            {
                "schema_version": FORGE_SCHEMA_VERSION,
                "run_id": run_id,
                "evidence_class": "SIMULATED",
                "synthetic": True,
                "step": step,
                "observed_at": observed_at.isoformat(),
                "input_tokens": step * simulation["input_tokens_per_step"],
                "peak_host_bytes": simulation["peak_host_bytes"],
                "peak_device_bytes": simulation["peak_device_bytes"],
                "energy_wh": step * simulation["energy_wh_per_step"],
                "temperature_millic": simulation["max_temperature_millic"],
                "synthetic_loss_millionths": synthetic_loss,
            }
        )

    telemetry_path = run_dir / "telemetry.jsonl"
    _atomic_write_text(
        telemetry_path,
        "".join(qmf_canonical_json(event) + "\n" for event in telemetry),
    )
    candidate_body = {
        "schema_version": FORGE_SCHEMA_VERSION,
        "run_id": run_id,
        "evidence_class": "SIMULATED",
        "artifact_kind": "synthetic-training-shape",
        "not_a_model": True,
        "not_a_peft_adapter": True,
        "qmf_admissible": False,
        "plan_hash": plan_hash,
        "checkpoint_chain_head": previous,
    }
    candidate = dict(candidate_body)
    candidate["candidate_hash"] = qmf_digest(candidate_body)
    candidate_path = candidate_dir / "synthetic-candidate.json"
    atomic_write_json(candidate_path, candidate)

    completed = started + timedelta(seconds=simulation["steps"] * step_duration)
    receipt = {
        "@context": "https://oims.collective-osp.org/model-forge/v1",
        "@type": "OIMSModelForgeRunReceipt",
        "schema_version": FORGE_SCHEMA_VERSION,
        "run_id": run_id,
        "plan_id": plan["plan_id"],
        "plan_hash": plan_hash,
        "mode": "simulate",
        "status": "COMPLETED",
        "evidence_class": "SIMULATED",
        "synthetic": True,
        "qmf_admissible": False,
        "deployable_artifact": False,
        "authority": "none",
        "started_at": started.isoformat(),
        "completed_at": completed.isoformat(),
        "steps": simulation["steps"],
        "input_tokens": simulation["steps"] * simulation["input_tokens_per_step"],
        "output_bytes": simulation["steps"] * simulation["output_bytes_per_checkpoint"],
        "duration_seconds": simulation["steps"] * step_duration,
        "peak_host_bytes": simulation["peak_host_bytes"],
        "peak_device_bytes": simulation["peak_device_bytes"],
        "energy_wh": simulation["steps"] * simulation["energy_wh_per_step"],
        "cost_microusd": 0,
        "max_temperature_millic": simulation["max_temperature_millic"],
        "network_mode": "none",
        "swap_used": False,
        "telemetry_file": "telemetry.jsonl",
        "telemetry_hash": prefixed_file_digest(telemetry_path),
        "checkpoint_directory": "checkpoints",
        "checkpoint_count": len(checkpoint_hashes),
        "checkpoint_chain_head": previous,
        "candidate_file": "candidate/synthetic-candidate.json",
        "candidate_hash": candidate["candidate_hash"],
        "rollback_artifact_hash": plan["qmf_contract"]["rollback_artifact_hash"],
        "governance_route": GOVERNANCE_ROUTE,
        "limitations": SIMULATION_LIMITATIONS,
        "source_commit": _forge_source_commit(),
    }
    sealed = seal_record(receipt)
    atomic_write_json(run_dir / "receipt.json", sealed)
    return sealed


def _load_json_object(
    path: Path,
    label: str,
    *,
    max_bytes: int = MAX_RECORD_BYTES,
) -> dict[str, Any]:
    try:
        size = path.stat().st_size
        if size > max_bytes:
            raise ForgePlanError(f"{label} exceeds {max_bytes} bytes")
        value = _strict_json_loads(path.read_text(encoding="utf-8"))
    except ForgePlanError:
        raise
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise ForgePlanError(f"cannot load {label} {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ForgePlanError(f"{label} root must be an object")
    return value


def verify_forge_run(receipt_path: Path | str) -> dict[str, Any]:
    try:
        path = Path(receipt_path).resolve()
    except (OSError, RuntimeError) as exc:
        return {
            "valid": False,
            "receipt_path": str(receipt_path),
            "errors": [f"cannot resolve Forge receipt path: {exc}"],
        }
    errors: list[str] = []
    try:
        receipt = _load_json_object(path, "Forge receipt")
    except ForgePlanError as exc:
        return {"valid": False, "receipt_path": str(path), "errors": [str(exc)]}
    if not verify_sealed_record(receipt):
        errors.append("Forge receipt seal is invalid")
    if set(receipt) != RUN_RECEIPT_KEYS:
        errors.append("Forge receipt fields do not match the strict receipt contract")
    expected_receipt = {
        "@context": "https://oims.collective-osp.org/model-forge/v1",
        "@type": "OIMSModelForgeRunReceipt",
        "schema_version": FORGE_SCHEMA_VERSION,
        "mode": "simulate",
        "status": "COMPLETED",
        "evidence_class": "SIMULATED",
        "synthetic": True,
        "qmf_admissible": False,
        "deployable_artifact": False,
        "authority": "none",
        "network_mode": "none",
        "swap_used": False,
        "telemetry_file": "telemetry.jsonl",
        "checkpoint_directory": "checkpoints",
        "candidate_file": "candidate/synthetic-candidate.json",
        "governance_route": GOVERNANCE_ROUTE,
        "limitations": SIMULATION_LIMITATIONS,
    }
    for field, expected in expected_receipt.items():
        if receipt.get(field) != expected or type(receipt.get(field)) is not type(expected):
            errors.append(f"Forge receipt field {field} is invalid")

    run_dir = path.parent
    plan_valid = False
    expected_run_id: str | None = None
    try:
        plan = _load_json_object(run_dir / "plan.json", "Forge plan")
    except ForgePlanError as exc:
        errors.append(str(exc))
        plan = {}
    else:
        plan_errors = validate_forge_plan(plan)
        errors.extend(f"plan: {error}" for error in plan_errors)
        plan_valid = not plan_errors and plan.get("mode") == "simulate"
        if receipt.get("plan_hash") != plan.get("plan_hash"):
            errors.append("Forge receipt plan hash link is invalid")
    if plan_valid:
        simulation = plan["simulation"]
        started = _parse_timestamp(simulation["clock_start"])
        if started is None:  # guarded by the plan validator
            plan_valid = False
        else:
            completed = started + timedelta(
                seconds=simulation["steps"] * simulation["step_duration_seconds"]
            )
            expected_run_id = f"sim-{plan['plan_hash'].removeprefix('sha256:')[:16]}"
            expected_dynamic_receipt = {
                "run_id": expected_run_id,
                "plan_id": plan["plan_id"],
                "plan_hash": plan["plan_hash"],
                "started_at": started.isoformat(),
                "completed_at": completed.isoformat(),
                "steps": simulation["steps"],
                "input_tokens": simulation["steps"] * simulation["input_tokens_per_step"],
                "output_bytes": simulation["steps"] * simulation["output_bytes_per_checkpoint"],
                "duration_seconds": simulation["steps"] * simulation["step_duration_seconds"],
                "peak_host_bytes": simulation["peak_host_bytes"],
                "peak_device_bytes": simulation["peak_device_bytes"],
                "energy_wh": simulation["steps"] * simulation["energy_wh_per_step"],
                "cost_microusd": 0,
                "max_temperature_millic": simulation["max_temperature_millic"],
                "checkpoint_count": simulation["steps"],
                "rollback_artifact_hash": plan["qmf_contract"]["rollback_artifact_hash"],
            }
            for field, expected in expected_dynamic_receipt.items():
                if receipt.get(field) != expected or type(receipt.get(field)) is not type(expected):
                    errors.append(f"Forge receipt field {field} failed semantic replay")

    source_commit = receipt.get("source_commit")
    if source_commit is not None and not _is_revision(source_commit):
        errors.append("Forge receipt source_commit is invalid")

    telemetry_path = run_dir / str(receipt.get("telemetry_file", ""))
    telemetry_bytes: bytes | None = None
    if telemetry_path.is_symlink() or telemetry_path.resolve().parent != run_dir.resolve():
        errors.append("Forge telemetry path escaped the run directory")
    elif not telemetry_path.is_file():
        errors.append("Forge telemetry file is missing")
    else:
        try:
            if telemetry_path.stat().st_size > MAX_TELEMETRY_BYTES:
                raise ForgePlanError(f"Forge telemetry exceeds {MAX_TELEMETRY_BYTES} bytes")
            telemetry_bytes = telemetry_path.read_bytes()
        except (OSError, ForgePlanError) as exc:
            errors.append(str(exc))
        else:
            observed_hash = "sha256:" + hashlib.sha256(telemetry_bytes).hexdigest()
            if receipt.get("telemetry_hash") != observed_hash:
                errors.append("Forge telemetry hash is invalid")
    if telemetry_bytes is not None and plan_valid and started is not None:
        expected_events = []
        for step, synthetic_loss in enumerate(simulation["synthetic_loss_millionths"], start=1):
            expected_events.append(
                {
                    "schema_version": FORGE_SCHEMA_VERSION,
                    "run_id": expected_run_id,
                    "evidence_class": "SIMULATED",
                    "synthetic": True,
                    "step": step,
                    "observed_at": (
                        started + timedelta(seconds=step * simulation["step_duration_seconds"])
                    ).isoformat(),
                    "input_tokens": step * simulation["input_tokens_per_step"],
                    "peak_host_bytes": simulation["peak_host_bytes"],
                    "peak_device_bytes": simulation["peak_device_bytes"],
                    "energy_wh": step * simulation["energy_wh_per_step"],
                    "temperature_millic": simulation["max_temperature_millic"],
                    "synthetic_loss_millionths": synthetic_loss,
                }
            )
        expected_telemetry = "".join(
            qmf_canonical_json(event) + "\n" for event in expected_events
        ).encode("utf-8")
        if telemetry_bytes != expected_telemetry:
            errors.append("Forge telemetry failed semantic replay")

    checkpoint_dir = run_dir / str(receipt.get("checkpoint_directory", ""))
    if (
        checkpoint_dir.is_symlink()
        or checkpoint_dir.resolve().parent != run_dir.resolve()
        or not checkpoint_dir.is_dir()
    ):
        errors.append("Forge checkpoint directory is invalid")
        checkpoints: list[Path] = []
    else:
        try:
            checkpoints = sorted(checkpoint_dir.iterdir())
        except OSError as exc:
            errors.append(f"cannot enumerate Forge checkpoint directory: {exc}")
            checkpoints = []
        else:
            if any(path.is_symlink() or not path.is_file() for path in checkpoints):
                errors.append("Forge checkpoint directory contains a non-regular artifact")
    if receipt.get("checkpoint_count") != len(checkpoints):
        errors.append("Forge checkpoint count is invalid")
    previous: str | None = None
    for position, checkpoint_path in enumerate(checkpoints, start=1):
        if checkpoint_path.name != f"step-{position:06d}.json":
            errors.append(f"Forge checkpoint {position} filename is invalid")
        try:
            checkpoint = _load_json_object(checkpoint_path, "Forge checkpoint")
        except ForgePlanError as exc:
            errors.append(str(exc))
            continue
        if set(checkpoint) != SYNTHETIC_CHECKPOINT_KEYS:
            errors.append(f"Forge checkpoint {position} fields are invalid")
        claimed = checkpoint.pop("checkpoint_hash", None)
        if claimed != qmf_digest(checkpoint):
            errors.append(f"Forge checkpoint {position} hash is invalid")
        if checkpoint.get("step") != position:
            errors.append(f"Forge checkpoint {position} step is invalid")
        if checkpoint.get("previous_checkpoint_hash") != previous:
            errors.append(f"Forge checkpoint {position} breaks the hash chain")
        if checkpoint.get("plan_hash") != receipt.get("plan_hash"):
            errors.append(f"Forge checkpoint {position} plan binding is invalid")
        if plan_valid and position <= simulation["steps"]:
            expected_checkpoint = {
                "schema_version": FORGE_SCHEMA_VERSION,
                "run_id": expected_run_id,
                "evidence_class": "SIMULATED",
                "synthetic": True,
                "step": position,
                "previous_checkpoint_hash": previous,
                "plan_hash": plan["plan_hash"],
                "input_tokens": position * simulation["input_tokens_per_step"],
                "synthetic_loss_millionths": simulation["synthetic_loss_millionths"][position - 1],
                "synthetic_output_bytes": simulation["output_bytes_per_checkpoint"],
            }
            if checkpoint != expected_checkpoint:
                errors.append(f"Forge checkpoint {position} failed semantic replay")
        elif plan_valid:
            errors.append(f"Forge checkpoint {position} exceeds the simulated step count")
        previous = claimed if _is_digest(claimed) else None
    if receipt.get("checkpoint_chain_head") != previous:
        errors.append("Forge checkpoint chain head is invalid")

    candidate_path = run_dir / str(receipt.get("candidate_file", ""))
    if candidate_path.is_symlink() or candidate_path.resolve().parent.parent != run_dir.resolve():
        errors.append("Forge candidate path escaped the run directory")
    elif not candidate_path.is_file():
        errors.append("Forge synthetic candidate is missing")
    else:
        try:
            candidate = _load_json_object(candidate_path, "Forge synthetic candidate")
        except ForgePlanError as exc:
            errors.append(str(exc))
        else:
            if set(candidate) != CANDIDATE_KEYS:
                errors.append("Forge synthetic candidate fields are invalid")
            claimed = candidate.pop("candidate_hash", None)
            if claimed != qmf_digest(candidate) or claimed != receipt.get("candidate_hash"):
                errors.append("Forge synthetic candidate hash is invalid")
            if not (
                candidate.get("not_a_model") is True
                and candidate.get("not_a_peft_adapter") is True
                and candidate.get("qmf_admissible") is False
            ):
                errors.append("Forge synthetic candidate boundary is invalid")
            if plan_valid:
                expected_candidate = {
                    "schema_version": FORGE_SCHEMA_VERSION,
                    "run_id": expected_run_id,
                    "evidence_class": "SIMULATED",
                    "artifact_kind": "synthetic-training-shape",
                    "not_a_model": True,
                    "not_a_peft_adapter": True,
                    "qmf_admissible": False,
                    "plan_hash": plan["plan_hash"],
                    "checkpoint_chain_head": previous,
                }
                if candidate != expected_candidate:
                    errors.append("Forge synthetic candidate failed semantic replay")
    return {
        "valid": not errors,
        "receipt_path": str(path),
        "run_id": receipt.get("run_id"),
        "evidence_class": receipt.get("evidence_class"),
        "qmf_admissible": False,
        "errors": errors,
    }


def _proc_status() -> dict[str, str]:
    result: dict[str, str] = {}
    try:
        for line in Path("/proc/self/status").read_text(encoding="utf-8").splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                result[key] = value.strip()
    except OSError:
        return {}
    return result


def _memory_info() -> dict[str, int]:
    result: dict[str, int] = {}
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            parts = value.strip().split()
            if parts and parts[0].isdigit():
                result[key] = int(parts[0]) * 1024
    except OSError:
        return {}
    return result


def _root_is_read_only() -> bool:
    try:
        mounts = Path("/proc/mounts").read_text(encoding="utf-8").splitlines()
    except OSError:
        return False
    for line in mounts:
        fields = line.split()
        if len(fields) >= 4 and fields[1] == "/":
            return "ro" in fields[3].split(",")
    return False


def _default_route_present() -> bool:
    try:
        lines = Path("/proc/net/route").read_text(encoding="utf-8").splitlines()[1:]
    except OSError:
        return True
    return any(len(line.split()) >= 2 and line.split()[1] == "00000000" for line in lines)


def _network_interfaces() -> set[str]:
    try:
        return {path.name for path in Path("/sys/class/net").iterdir()}
    except OSError:
        return set()


def _forge_mount_policy() -> dict[str, bool]:
    targets = {
        "/forge/plan.json": "plan_read_only",
        "/forge/inputs/base": "base_model_read_only",
        "/forge/inputs/dataset": "dataset_read_only",
        "/forge/output": "output_writable",
        "/tmp": "tmpfs_active",
    }
    result = {name: False for name in targets.values()}
    try:
        lines = Path("/proc/self/mountinfo").read_text(encoding="utf-8").splitlines()
    except OSError:
        return result
    for line in lines:
        before, separator, after = line.partition(" - ")
        if not separator:
            continue
        fields = before.split()
        filesystem_fields = after.split()
        if len(fields) < 6 or not filesystem_fields:
            continue
        mountpoint = fields[4].replace("\\040", " ")
        observation = targets.get(mountpoint)
        if observation is None:
            continue
        options = set(fields[5].split(","))
        if observation == "output_writable":
            result[observation] = "rw" in options and "ro" not in options
        elif observation == "tmpfs_active":
            result[observation] = filesystem_fields[0] == "tmpfs"
        else:
            result[observation] = "ro" in options and "rw" not in options
    return result


def _cgroup_limits() -> dict[str, int | None]:
    def read_limit(path: Path) -> int | None:
        try:
            value = path.read_text(encoding="utf-8").strip()
        except OSError:
            return None
        return int(value) if value.isdigit() else None

    memory_limit = read_limit(Path("/sys/fs/cgroup/memory.max"))
    swap_limit = read_limit(Path("/sys/fs/cgroup/memory.swap.max"))
    pids_limit = read_limit(Path("/sys/fs/cgroup/pids.max"))
    if memory_limit is None:
        memory_limit = read_limit(Path("/sys/fs/cgroup/memory/memory.limit_in_bytes"))
        memory_and_swap = read_limit(Path("/sys/fs/cgroup/memory/memory.memsw.limit_in_bytes"))
        if memory_limit is not None and memory_and_swap is not None:
            swap_limit = max(0, memory_and_swap - memory_limit)
    if pids_limit is None:
        pids_limit = read_limit(Path("/sys/fs/cgroup/pids/pids.max"))
    return {
        "memory_limit_bytes": memory_limit,
        "swap_limit_bytes": swap_limit,
        "pids_limit": pids_limit,
    }


def inspect_physical_preflight(
    plan: dict[str, Any],
    *,
    accepted_plan_hash: str,
    environment: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Inspect a locked sandbox without loading weights or starting training."""

    errors = list(validate_forge_plan(plan))
    if plan.get("mode") != "probe":
        errors.append("only a probe plan can enter physical preflight")
    if accepted_plan_hash != plan.get("plan_hash"):
        errors.append("accepted plan hash does not match the exact Forge plan")
    env = environment if environment is not None else dict(os.environ)
    errors.extend(forge_container_environment_errors(env, require_probe_unlock=True))
    base_image_pinned = _is_immutable_image_ref(env.get("OIMS_FORGE_BASE_IMAGE"))

    status = _proc_status()
    effective_user_non_root = hasattr(os, "geteuid") and os.geteuid() != 0
    if not effective_user_non_root:
        errors.append("Forge physical preflight is not running as a non-root user")
    if status.get("CapEff") != "0000000000000000":
        errors.append("effective Linux capabilities are not empty")
    if status.get("NoNewPrivs") != "1":
        errors.append("no-new-privileges is not active")
    if status.get("Seccomp") != "2":
        errors.append("the runtime-default seccomp filter is not active")
    root_read_only = _root_is_read_only()
    default_route_present = _default_route_present()
    network_interfaces = _network_interfaces()
    only_loopback = network_interfaces == {"lo"}
    mount_policy = _forge_mount_policy()
    cgroup_limits = _cgroup_limits()
    if not root_read_only:
        errors.append("container root filesystem is not read-only")
    if default_route_present:
        errors.append("a default network route is present")
    if not only_loopback:
        errors.append("the offline sandbox exposes a non-loopback network interface")
    for observation, valid in mount_policy.items():
        if not valid:
            errors.append(f"Forge mount policy observation {observation} is not satisfied")

    memory = _memory_info()
    swap_total = memory.get("SwapTotal", -1)
    swap_free = memory.get("SwapFree", -2)
    if swap_total < 0 or swap_free < 0 or swap_total != swap_free:
        errors.append("swap is active or cannot be proven unused")
    host_memory = memory.get("MemTotal")
    resources = plan.get("resources")
    host_limit = resources.get("max_peak_host_bytes") if isinstance(resources, dict) else None
    if not _is_int(host_memory, minimum=1) or (
        _is_int(host_limit, minimum=1) and host_memory < host_limit
    ):
        errors.append("physical host memory is below the plan's host-memory ceiling")
    if not _is_int(cgroup_limits["memory_limit_bytes"], minimum=1) or (
        _is_int(host_limit, minimum=1) and cgroup_limits["memory_limit_bytes"] < host_limit
    ):
        errors.append("container memory limit is below the plan's host-memory ceiling")
    if cgroup_limits["swap_limit_bytes"] != 0:
        errors.append("container swap limit is not zero")
    if not _is_int(cgroup_limits["pids_limit"], minimum=1) or cgroup_limits["pids_limit"] > 512:
        errors.append("container PID limit is missing or exceeds 512")

    gpu: dict[str, Any] | None = None
    if not errors:
        command = [
            "nvidia-smi",
            f"--id={plan['resources']['device_id']}",
            "--query-gpu=uuid,name,memory.total,memory.used,temperature.gpu,power.draw,power.limit",
            "--format=csv,noheader,nounits",
        ]
        try:
            completed = subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
                timeout=15,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            errors.append(f"cannot inspect NVIDIA device: {exc}")
        else:
            fields = [field.strip() for field in completed.stdout.strip().split(",")]
            if len(fields) != 7:
                errors.append("nvidia-smi returned an unexpected field count")
            else:
                try:
                    total_bytes = int(float(fields[2]) * 1024 * 1024)
                    used_bytes = int(float(fields[3]) * 1024 * 1024)
                    temperature = int(float(fields[4]) * 1000)
                    power_milliwatts = int(float(fields[5]) * 1000)
                    power_limit_milliwatts = int(float(fields[6]) * 1000)
                except ValueError:
                    errors.append("nvidia-smi returned malformed numeric evidence")
                else:
                    gpu = {
                        "uuid": fields[0],
                        "name": fields[1],
                        "total_bytes": total_bytes,
                        "used_bytes": used_bytes,
                        "temperature_millic": temperature,
                        "power_milliwatts": power_milliwatts,
                        "power_limit_milliwatts": power_limit_milliwatts,
                    }
                    declared_device_bytes = next(
                        domain["capacity_bytes"]
                        for domain in plan["resources"]["memory_domains"]
                        if domain["kind"] == "gpu-vram"
                    )
                    if fields[1] != "NVIDIA GeForce RTX 4090":
                        errors.append("physical GPU identity is not the reviewed RTX 4090 target")
                    if abs(total_bytes - declared_device_bytes) > 512 * 1024**2:
                        errors.append(
                            "physical GPU memory does not match the declared memory domain"
                        )
                    if total_bytes - used_bytes < plan["resources"]["max_peak_device_bytes"]:
                        errors.append("available GPU memory is below the plan's device ceiling")
                    if temperature > plan["resources"]["max_temperature_millic"]:
                        errors.append("physical GPU temperature exceeds the plan ceiling")

    receipt = {
        "@context": "https://oims.collective-osp.org/model-forge/v1",
        "@type": "OIMSModelForgePreflightReceipt",
        "schema_version": FORGE_SCHEMA_VERSION,
        "plan_id": plan.get("plan_id"),
        "plan_hash": plan.get("plan_hash"),
        "mode": "probe",
        "status": "READY" if not errors else "REFUSED",
        "lawful": not errors,
        "evidence_class": "PHYSICAL_PREFLIGHT",
        "weights_loaded": False,
        "training_started": False,
        "qmf_admissible": False,
        "deployable_artifact": False,
        "network_mode": "none",
        "sandbox_observation": {
            "effective_user_non_root": effective_user_non_root,
            "capabilities_empty": status.get("CapEff") == "0000000000000000",
            "no_new_privileges": status.get("NoNewPrivs") == "1",
            "seccomp_filter": status.get("Seccomp") == "2",
            "read_only_root": root_read_only,
            "default_route_present": default_route_present,
            "only_loopback_interface": only_loopback,
            "base_image_pinned": base_image_pinned,
            **mount_policy,
            "swap_total_bytes": swap_total,
            "swap_used_bytes": (
                swap_total - swap_free if swap_total >= 0 and swap_free >= 0 else None
            ),
            "host_memory_bytes": host_memory,
            "container_memory_limit_bytes": cgroup_limits["memory_limit_bytes"],
            "container_swap_limit_bytes": cgroup_limits["swap_limit_bytes"],
            "container_pids_limit": cgroup_limits["pids_limit"],
        },
        "gpu": gpu,
        "errors": errors,
        "governance_route": GOVERNANCE_ROUTE,
        "source_commit": _forge_source_commit(env),
    }
    return seal_record(receipt)
