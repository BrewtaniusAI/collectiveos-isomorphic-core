from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml

from tools.build_openai_plugin import (
    PLUGIN_NAME,
    STARTER_SKILLS,
    build_marketplace,
    build_plugin,
)

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / PLUGIN_NAME
MARKETPLACE = ROOT / ".agents" / "plugins" / "marketplace.json"


def canonical_digest(name: str) -> str:
    package = ROOT / "skills" / name
    digest = hashlib.sha256()
    for relative in ("SKILL.md", "skill.yaml", "tests/evals.yaml"):
        data = (package / relative).read_bytes()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(data)
        digest.update(b"\0")
    return digest.hexdigest()


def test_committed_openai_plugin_is_skills_only_and_non_authorizing() -> None:
    plugin = json.loads((PLUGIN / "plugin.json").read_text(encoding="utf-8"))
    source = json.loads((PLUGIN / "COLLECTIVE_SOURCE.json").read_text(encoding="utf-8"))
    assert plugin["name"] == PLUGIN_NAME
    assert "mcpServers" not in plugin
    assert not (PLUGIN / "mcp.json").exists()
    assert source["authority_class"] == "proposal_and_evidence_only"
    assert source["authorizes_execution"] is False
    assert source["authorizes_external_writes"] is False
    assert source["authorizes_canonical_commit"] is False


def test_projected_skills_preserve_draft_boundary_and_source_content() -> None:
    source = json.loads((PLUGIN / "COLLECTIVE_SOURCE.json").read_text(encoding="utf-8"))
    records = {item["name"]: item for item in source["canonical_skills"]}
    for name in STARTER_SKILLS:
        canonical_dir = ROOT / "skills" / name
        projected_dir = PLUGIN / "skills" / name
        canonical_manifest = yaml.safe_load(
            (canonical_dir / "skill.yaml").read_text(encoding="utf-8")
        )
        projected = (projected_dir / "SKILL.md").read_text(encoding="utf-8")
        assert projected.startswith("---\n")
        assert f"name: {name}\n" in projected
        assert (canonical_dir / "SKILL.md").read_text(encoding="utf-8").strip() in projected
        assert canonical_manifest["status"] == "draft"
        assert canonical_manifest["runtime_activation"] is False
        assert records[name]["sha256"] == canonical_digest(name)
        assert (projected_dir / "references" / "skill.yaml").read_bytes() == (
            canonical_dir / "skill.yaml"
        ).read_bytes()
        assert (projected_dir / "references" / "evals.yaml").read_bytes() == (
            canonical_dir / "tests/evals.yaml"
        ).read_bytes()


def test_repo_marketplace_points_only_to_bounded_preview_plugin() -> None:
    marketplace = json.loads(MARKETPLACE.read_text(encoding="utf-8"))
    assert marketplace["name"] == "collectiveos"
    assert len(marketplace["plugins"]) == 1
    entry = marketplace["plugins"][0]
    assert entry["name"] == PLUGIN_NAME
    assert entry["source"] == {
        "source": "local",
        "path": "./plugins/collectiveos-core-preview",
    }
    assert entry["policy"]["installation"] == "AVAILABLE"


def test_builder_reproduces_structural_contract(tmp_path: Path) -> None:
    plugin_dir = tmp_path / "plugin"
    marketplace_path = tmp_path / ".agents" / "plugins" / "marketplace.json"
    boundary = build_plugin(plugin_dir)
    build_marketplace(marketplace_path)
    assert boundary["authorizes_execution"] is False
    assert {item["name"] for item in boundary["canonical_skills"]} == set(STARTER_SKILLS)
    assert (
        json.loads((plugin_dir / "plugin.json").read_text(encoding="utf-8"))["name"] == PLUGIN_NAME
    )
    assert (
        json.loads(marketplace_path.read_text(encoding="utf-8"))["plugins"][0]["name"]
        == PLUGIN_NAME
    )
