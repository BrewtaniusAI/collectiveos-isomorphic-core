from __future__ import annotations

from collections import deque
from typing import Any

_ALLOWED_OUTPUT_AUTHORITY = {"proposal", "candidate", "evidence"}


def _governed_binding(binding: dict[str, Any]) -> bool:
    return (
        binding.get("verification_required") is True
        and isinstance(binding.get("verifier"), str)
        and binding.get("verifier") not in {"", "none"}
        and binding.get("output_authority") in _ALLOWED_OUTPUT_AUTHORITY
        and isinstance(binding.get("input_artifact"), str)
        and isinstance(binding.get("output_artifact"), str)
    )


def resolve_path(
    catalog: dict[str, Any], source_artifact: str, target_artifact: str
) -> list[dict[str, Any]]:
    if source_artifact == target_artifact:
        return []

    bindings = [
        binding
        for binding in catalog.get("bindings", [])
        if isinstance(binding, dict) and _governed_binding(binding)
    ]
    by_input: dict[str, list[dict[str, Any]]] = {}
    for binding in bindings:
        by_input.setdefault(binding["input_artifact"], []).append(binding)
    for edges in by_input.values():
        edges.sort(key=lambda edge: edge.get("binding_id", ""))

    queue: deque[tuple[str, list[dict[str, Any]]]] = deque([(source_artifact, [])])
    visited = {source_artifact}
    while queue:
        artifact, path = queue.popleft()
        for binding in by_input.get(artifact, []):
            output = binding["output_artifact"]
            next_path = [*path, binding]
            if output == target_artifact:
                return next_path
            if output not in visited:
                visited.add(output)
                queue.append((output, next_path))
    return []
