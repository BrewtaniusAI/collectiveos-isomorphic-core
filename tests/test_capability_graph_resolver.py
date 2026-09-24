from __future__ import annotations

import json
from pathlib import Path

from tools.resolve_capability_graph import resolve_path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "examples" / "capability-graph.meshy-game-studio.v1.json"


def _catalog() -> dict:
    return json.loads(CATALOG.read_text(encoding="utf-8"))


def test_resolver_finds_cross_provider_artifact_path() -> None:
    path = resolve_path(_catalog(), "character-spec", "browser-playback-evidence")
    assert [edge["binding_id"] for edge in path] == [
        "meshy-rigged-character",
        "game-studio-web-projection",
        "game-studio-browser-smoke",
    ]


def test_resolver_rejects_unverified_shortcut() -> None:
    catalog = _catalog()
    catalog["bindings"].insert(
        0,
        {
            "binding_id": "unsafe-shortcut",
            "skill_id": "shortcut",
            "actuator": "provider",
            "input_artifact": "character-spec",
            "output_artifact": "browser-playback-evidence",
            "output_authority": "candidate",
            "verifier": "none",
            "verification_required": False,
        },
    )
    path = resolve_path(catalog, "character-spec", "browser-playback-evidence")
    assert all(edge["binding_id"] != "unsafe-shortcut" for edge in path)


def test_resolver_returns_empty_when_no_governed_path_exists() -> None:
    assert resolve_path(_catalog(), "character-spec", "canonical-asset") == []


def test_resolver_rejects_authorizing_catalog_root() -> None:
    catalog = _catalog()
    catalog["authority"]["authorizes_execution"] = True
    assert resolve_path(catalog, "character-spec", "browser-playback-evidence") == []


def test_resolver_rejects_non_declarative_catalog_status() -> None:
    catalog = _catalog()
    catalog["status"] = "ACTIVE_AUTHORITY"
    assert resolve_path(catalog, "character-spec", "browser-playback-evidence") == []

[executed on device: Marks-Mac-mini.local (cc335bcf-2fab-4eac-84d3-b9e5551bc3a3)]