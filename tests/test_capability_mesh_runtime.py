from __future__ import annotations

import json
from pathlib import Path

from tools.compile_capability_mesh import compile_mesh
from tools.resolve_capability_graph import resolve_path

ROOT = Path(__file__).resolve().parents[1]
PROOF = ROOT / "examples" / "capability-mesh-runtime-proof.v1.json"


def test_public_runtime_proof_compiles_and_routes_deterministically() -> None:
    proof = json.loads(PROOF.read_text(encoding="utf-8"))
    inventory = json.loads((ROOT / proof["inventory"]).read_text(encoding="utf-8"))
    templates = json.loads((ROOT / proof["templates"]).read_text(encoding="utf-8"))

    graph = compile_mesh(inventory, templates)
    path = resolve_path(
        graph,
        proof["request"]["source_artifact"],
        proof["request"]["target_artifact"],
    )

    assert [edge["binding_id"] for edge in path] == proof["expected_binding_ids"]


def test_public_runtime_proof_rejects_constraint_incompatible_route() -> None:
    proof = json.loads(PROOF.read_text(encoding="utf-8"))
    inventory = json.loads((ROOT / proof["inventory"]).read_text(encoding="utf-8"))
    templates = json.loads((ROOT / proof["templates"]).read_text(encoding="utf-8"))
    graph = compile_mesh(inventory, templates)

    for constraints in proof["rejection_constraints"]:
        assert (
            resolve_path(
                graph,
                proof["request"]["source_artifact"],
                proof["request"]["target_artifact"],
                constraints=constraints,
            )
            == []
        )
