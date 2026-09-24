from __future__ import annotations

from collections import deque
from typing import Any

_ALLOWED_OUTPUT_AUTHORITY = {"proposal", "candidate", "evidence"}
_ALLOWED_LOCALITY = {"local", "remote", "hybrid"}
_COST_ORDER = {"free": 0, "metered": 1, "unknown": 2}
_REQUIRED_FALSE_AUTHORITY = (
    "authorizes_execution",
    "authorizes_external_writes",
    "authorizes_canonical_commit",
    "authorizes_governance_promotion",
)
_ALLOWED_CONSTRAINT_KEYS = {
    "allowed_locality",
    "max_cost_class",
    "required_providers",
    "denied_providers",
    "max_hops",
}


def _catalog_is_non_authorizing(catalog: dict[str, Any]) -> bool:
    if catalog.get("schema") != "collective.capability-graph.v1":
        return False
    if catalog.get("status") != "DECLARATIVE_NON_AUTHORIZING":
        return False
    authority = catalog.get("authority")
    if not isinstance(authority, dict) or authority.get("routing_is_advisory") is not True:
        return False
    return all(authority.get(key) is False for key in _REQUIRED_FALSE_AUTHORITY)


def _governed_binding(binding: dict[str, Any]) -> bool:
    return (
        binding.get("verification_required") is True
        and isinstance(binding.get("verifier"), str)
        and binding.get("verifier") not in {"", "none"}
        and binding.get("output_authority") in _ALLOWED_OUTPUT_AUTHORITY
        and isinstance(binding.get("input_artifact"), str)
        and isinstance(binding.get("output_artifact"), str)
    )


def _valid_constraints(constraints: dict[str, Any]) -> bool:
    if set(constraints) - _ALLOWED_CONSTRAINT_KEYS:
        return False

    allowed_locality = constraints.get("allowed_locality")
    if allowed_locality is not None:
        if not isinstance(allowed_locality, list) or not allowed_locality:
            return False
        if any(value not in _ALLOWED_LOCALITY for value in allowed_locality):
            return False

    max_cost_class = constraints.get("max_cost_class")
    if max_cost_class is not None and max_cost_class not in _COST_ORDER:
        return False

    for key in ("required_providers", "denied_providers"):
        value = constraints.get(key)
        if value is not None:
            if not isinstance(value, list):
                return False
            if any(not isinstance(provider, str) or not provider for provider in value):
                return False

    max_hops = constraints.get("max_hops")
    return not (
        max_hops is not None
        and (not isinstance(max_hops, int) or isinstance(max_hops, bool) or max_hops < 1)
    )


def _binding_satisfies_constraints(binding: dict[str, Any], constraints: dict[str, Any]) -> bool:
    allowed_locality = constraints.get("allowed_locality")
    if allowed_locality is not None and binding.get("locality") not in set(allowed_locality):
        return False

    max_cost_class = constraints.get("max_cost_class")
    if max_cost_class is not None:
        cost_class = binding.get("cost_class")
        if cost_class not in _COST_ORDER:
            return False
        if _COST_ORDER[cost_class] > _COST_ORDER[max_cost_class]:
            return False

    providers = binding.get("providers")
    required = constraints.get("required_providers")
    denied = constraints.get("denied_providers")
    if required is not None or denied is not None:
        if not isinstance(providers, list) or any(not isinstance(item, str) for item in providers):
            return False
        provider_set = set(providers)
        if required is not None and not set(required).issubset(provider_set):
            return False
        if denied is not None and provider_set.intersection(denied):
            return False

    return True


def resolve_path(
    catalog: dict[str, Any],
    source_artifact: str,
    target_artifact: str,
    *,
    constraints: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    if not _catalog_is_non_authorizing(catalog):
        return []
    if source_artifact == target_artifact:
        return []

    active_constraints = constraints or {}
    if not isinstance(active_constraints, dict) or not _valid_constraints(active_constraints):
        return []

    bindings = [
        binding
        for binding in catalog.get("bindings", [])
        if isinstance(binding, dict)
        and _governed_binding(binding)
        and _binding_satisfies_constraints(binding, active_constraints)
    ]
    by_input: dict[str, list[dict[str, Any]]] = {}
    for binding in bindings:
        by_input.setdefault(binding["input_artifact"], []).append(binding)
    for edges in by_input.values():
        edges.sort(key=lambda edge: edge.get("binding_id", ""))

    max_hops = active_constraints.get("max_hops")
    queue: deque[tuple[str, list[dict[str, Any]]]] = deque([(source_artifact, [])])
    visited = {source_artifact}
    while queue:
        artifact, path = queue.popleft()
        if max_hops is not None and len(path) >= max_hops:
            continue
        for binding in by_input.get(artifact, []):
            output = binding["output_artifact"]
            next_path = [*path, binding]
            if output == target_artifact:
                return next_path
            if output not in visited:
                visited.add(output)
                queue.append((output, next_path))
    return []
