"""CollectiveOS request/response bridge with explicit role binding."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from .agents import AgentProfile, AgentRegistry, load_agent_registry
from .backends import InferenceBackend, LlamaCppBackend
from .manifest import FamilyManifest, TierSpec, load_manifest
from .proof import atomic_write_json, seal_record, sha256_value, utc_now
from .runtime import DEFAULT_ARTIFACTS_DIR, DEFAULT_WEIGHTS_DIR, run_tier

ProfileBackendFactory = Callable[[TierSpec, AgentProfile], InferenceBackend]


class CollectiveRequestError(ValueError):
    """Raised when the CollectiveOS request envelope is invalid."""


def run_collective_request(
    request: dict[str, Any],
    *,
    manifest: FamilyManifest | None = None,
    registry: AgentRegistry | None = None,
    backend_factory: ProfileBackendFactory | None = None,
    weights_dir: Path = DEFAULT_WEIGHTS_DIR,
    artifacts_dir: Path = DEFAULT_ARTIFACTS_DIR,
) -> dict[str, Any]:
    manifest = manifest or load_manifest()
    registry = registry or load_agent_registry(manifest=manifest)
    if not isinstance(request, dict):
        raise CollectiveRequestError("CollectiveOS request must be a JSON object")
    unknown = sorted(set(request) - {"request_id", "agent", "prompt", "max_tokens"})
    if unknown:
        raise CollectiveRequestError(
            f"CollectiveOS request contains unsupported fields: {', '.join(unknown)}"
        )
    prompt = request.get("prompt")
    if not isinstance(prompt, str):
        raise CollectiveRequestError("CollectiveOS request prompt must be a string")
    agent_name = request.get("agent")
    if agent_name is not None and not isinstance(agent_name, str):
        raise CollectiveRequestError("CollectiveOS request agent must be a string")
    request_id_value = request.get("request_id")
    if request_id_value is not None and (
        not isinstance(request_id_value, str) or not request_id_value
    ):
        raise CollectiveRequestError("CollectiveOS request_id must be a nonempty string")
    try:
        max_tokens = int(request.get("max_tokens", 256))
    except (TypeError, ValueError) as exc:
        raise CollectiveRequestError("max_tokens must be an integer") from exc
    if max_tokens <= 0 or max_tokens > 4096:
        raise CollectiveRequestError("max_tokens must be between 1 and 4096")

    profile = registry.resolve(agent_name)
    request_hash = sha256_value(request)
    request_id = request_id_value or f"oims-{request_hash[:16]}"
    binding = registry.binding(profile)
    factory = backend_factory or (
        lambda spec, selected: LlamaCppBackend(
            spec,
            weights_root=weights_dir,
            system_prompt=selected.system_prompt,
        )
    )
    result = run_tier(
        profile.tier,
        prompt,
        manifest=manifest,
        backend_factory=lambda spec: factory(spec, profile),
        weights_dir=weights_dir,
        artifacts_dir=artifacts_dir,
        max_tokens=max_tokens,
        agent_binding=binding,
    )
    response = {
        "@context": "https://oims.collective-osp.org/collective/v1",
        "@type": "CollectiveOIMSResponse",
        "schema_version": 1,
        "created_at": utc_now(),
        "request_id": request_id,
        "request_sha256": request_hash,
        "activation_semantics": registry.activation_semantics,
        "autonomous_worker_claim": registry.autonomous_worker_claim,
        "governance_route": list(registry.governance_route),
        "agent_manifest_sha256": registry.source_hash,
        "agent_binding": binding,
        "result_record_sha256": result["record_sha256"],
        "result": result,
    }
    sealed = seal_record(response)
    atomic_write_json(
        artifacts_dir / f"collective-{request_hash[:16]}.jsonld",
        sealed,
    )
    return sealed
