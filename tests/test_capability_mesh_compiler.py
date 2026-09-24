from __future__ import annotations

import copy
import json
from pathlib import Path

from tools.compile_capability_mesh import compile_mesh

ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "examples" / "capability-inventory.sanitized.v1.json"
TEMPLATES = ROOT / "examples" / "capability-binding-templates.v1.json"


def _inventory() -> dict:
    return json.loads(INVENTORY.read_text(encoding="utf-8"))


def _templates() -> dict:
    return json.loads(TEMPLATES.read_text(encoding="utf-8"))


def test_compiler_activates_cross_provider_bindings_deterministically() -> None:
    graph = compile_mesh(_inventory(), _templates())
    ids = [item["binding_id"] for item in graph["bindings"]]

    assert ids == sorted(ids)
    assert ids == [
        "game-studio-browser-smoke",
        "game-studio-web-projection",
        "meshy-rigged-character",
    ]
    web = next(
        item for item in graph["bindings"] if item["binding_id"] == "game-studio-web-projection"
    )
    assert set(web["providers"]) == {"CollectiveOS", "Game Studio", "Local CLI"}


def test_compiler_excludes_binding_when_actuator_is_missing() -> None:
    inventory = _inventory()
    inventory["capabilities"] = [
        item for item in inventory["capabilities"] if item["capability_id"] != "gltf-transform"
    ]
    graph = compile_mesh(inventory, _templates())
    assert "game-studio-web-projection" not in {item["binding_id"] for item in graph["bindings"]}


def test_compiler_excludes_binding_when_verifier_is_missing() -> None:
    inventory = _inventory()
    inventory["capabilities"] = [
        item
        for item in inventory["capabilities"]
        if item["capability_id"] != "collective-rig-validator"
    ]
    graph = compile_mesh(inventory, _templates())
    assert "meshy-rigged-character" not in {item["binding_id"] for item in graph["bindings"]}


def test_compiler_excludes_binding_when_required_capability_is_unavailable() -> None:
    inventory = copy.deepcopy(_inventory())
    target = next(
        item for item in inventory["capabilities"] if item["capability_id"] == "threejs-playwright"
    )
    target["available"] = False
    graph = compile_mesh(inventory, _templates())
    assert "game-studio-browser-smoke" not in {item["binding_id"] for item in graph["bindings"]}


def test_compiler_excludes_role_confused_binding() -> None:
    inventory = copy.deepcopy(_inventory())
    target = next(
        item for item in inventory["capabilities"] if item["capability_id"] == "gltf-transform"
    )
    target["kind"] = "verifier"

    graph = compile_mesh(inventory, _templates())

    assert "game-studio-web-projection" not in {item["binding_id"] for item in graph["bindings"]}


def test_compiler_skips_malformed_template_without_raising() -> None:
    templates = copy.deepcopy(_templates())
    del templates["templates"][0]["binding_id"]

    graph = compile_mesh(_inventory(), templates)

    assert "meshy-rigged-character" not in {item["binding_id"] for item in graph["bindings"]}
