from __future__ import annotations

import copy
import json
from pathlib import Path

from tools.compile_capability_mesh import compile_mesh
from tools.resolve_capability_graph import resolve_path

ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "examples" / "capability-inventory.sanitized.v1.json"
TEMPLATES = ROOT / "examples" / "capability-binding-templates.v1.json"


def _graph() -> dict:
    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
    templates = json.loads(TEMPLATES.read_text(encoding="utf-8"))
    return compile_mesh(inventory, templates)


def test_local_only_constraint_excludes_remote_dependent_route() -> None:
    assert (
        resolve_path(
            _graph(),
            "character-spec",
            "browser-playback-evidence",
            constraints={"allowed_locality": ["local"]},
        )
        == []
    )


def test_free_cost_ceiling_excludes_metered_route() -> None:
    assert (
        resolve_path(
            _graph(),
            "character-spec",
            "browser-playback-evidence",
            constraints={"max_cost_class": "free"},
        )
        == []
    )


def test_provider_deny_excludes_matching_route() -> None:
    assert (
        resolve_path(
            _graph(),
            "character-spec",
            "browser-playback-evidence",
            constraints={"denied_providers": ["Meshy"]},
        )
        == []
    )


def test_required_provider_must_be_present_on_each_selected_binding() -> None:
    path = resolve_path(
        _graph(),
        "character-spec",
        "browser-playback-evidence",
        constraints={"required_providers": ["CollectiveOS"]},
    )
    assert len(path) == 3
    assert all("CollectiveOS" in edge["providers"] for edge in path)


def test_max_hops_bounds_route() -> None:
    assert (
        resolve_path(
            _graph(),
            "character-spec",
            "browser-playback-evidence",
            constraints={"max_hops": 2},
        )
        == []
    )
    assert (
        len(
            resolve_path(
                _graph(),
                "character-spec",
                "browser-playback-evidence",
                constraints={"max_hops": 3},
            )
        )
        == 3
    )


def test_constraints_do_not_override_unsafe_catalog_root() -> None:
    graph = copy.deepcopy(_graph())
    graph["authority"]["authorizes_execution"] = True
    assert (
        resolve_path(
            graph,
            "character-spec",
            "browser-playback-evidence",
            constraints={"max_cost_class": "unknown"},
        )
        == []
    )
