from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CANONICAL_SKILLS = ROOT / "skills"
STARTER_SKILLS = ("collective-os-core", "iere", "gaces")
PLUGIN_NAME = "collectiveos-core-preview"
PLUGIN_VERSION = "0.1.0"

DESCRIPTIONS = {
    "collective-os-core": "Use for non-trivial planning, system design, research synthesis, implementation planning, or risk-sensitive work that needs explicit constraints, verification, provenance, and bounded execution.",
    "iere": "Use when an answer depends on current facts, technical documentation, repositories, supplied artifacts, policy research, or multiple evidence streams that must be reconciled and cited.",
    "gaces": "Use before any create, update, delete, send, post, deploy, merge, schedule, purchase, or other persistent or external state change; require exact target resolution, approval, verification, and rollback evidence.",
}


def package_digest(package_dir: Path) -> str:
    digest = hashlib.sha256()
    for relative in ("SKILL.md", "skill.yaml", "tests/evals.yaml"):
        data = (package_dir / relative).read_bytes()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(data)
        digest.update(b"\0")
    return digest.hexdigest()


def load_manifest(package_dir: Path) -> dict[str, object]:
    data = yaml.safe_load((package_dir / "skill.yaml").read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TypeError(f"{package_dir}: invalid skill manifest")
    if data.get("name") != package_dir.name:
        raise ValueError(f"{package_dir}: skill name mismatch")
    return data


def render_skill(name: str, package_dir: Path, manifest: dict[str, object]) -> str:
    canonical = (package_dir / "SKILL.md").read_text(encoding="utf-8").strip()
    description = DESCRIPTIONS[name]
    boundary = (
        "CollectiveOS host-projection boundary: this is a skills-only preview of a canonical "
        "CollectiveOS package whose source manifest is currently status: "
        + str(manifest["status"])
        + " and runtime_activation: "
        + str(manifest["runtime_activation"]).lower()
        + ". Relevance does not grant authority. This projection cannot authorize execution, "
        "external writes, canonical commitment, or governance promotion. Preserve user approval "
        "and host permission requirements."
    )
    return (
        "---\n"
        + f"name: {name}\n"
        + "description: "
        + json.dumps(description)
        + "\n---\n\n> **"
        + boundary
        + "**\n\n"
        + canonical
        + "\n\n## Host projection requirements\n\n"
        + "- Treat references/skill.yaml as policy metadata, not as self-granted permissions.\n"
        + "- Treat references/evals.yaml as behavioral acceptance evidence, not as proof that the skill is safe for every deployment.\n"
        + "- Do not expand tools, credentials, write access, execution lanes, or governance authority beyond what the host and canonical manifest independently permit.\n"
        + "- Any persistent or external state change must route through gaces and the host's own approval/permission controls.\n"
        + "- Outputs from this hosted projection are proposals or evidence until admitted by the CollectiveOS trust boundary.\n"
    )


def build_plugin(destination: Path) -> dict[str, object]:
    destination.mkdir(parents=True, exist_ok=True)
    source_records: list[dict[str, object]] = []

    plugin = {
        "$schema": "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",
        "name": PLUGIN_NAME,
        "version": PLUGIN_VERSION,
        "description": "Proposal-only CollectiveOS host projection for constraint-governed planning, evidence synthesis, and state-change gating.",
        "repository": "https://github.com/BrewtaniusAI/collectiveos-isomorphic-core",
        "keywords": ["governance", "research", "verification", "operations", "agentic"],
        "extensions": {
            "com.openai": {
                "interface": {
                    "displayName": "CollectiveOS Core (Preview)",
                    "shortDescription": "Constraint-governed planning, evidence, and action gating.",
                }
            }
        },
    }
    (destination / "plugin.json").write_text(json.dumps(plugin, indent=2) + "\n", encoding="utf-8")

    for name in STARTER_SKILLS:
        source = CANONICAL_SKILLS / name
        manifest = load_manifest(source)
        if manifest.get("status") != "draft" or manifest.get("runtime_activation") is not False:
            raise ValueError(f"{name}: preview compiler expects draft/non-active canonical source")
        target = destination / "skills" / name
        refs = target / "references"
        refs.mkdir(parents=True, exist_ok=True)
        (target / "SKILL.md").write_text(render_skill(name, source, manifest), encoding="utf-8")
        shutil.copyfile(source / "skill.yaml", refs / "skill.yaml")
        shutil.copyfile(source / "tests/evals.yaml", refs / "evals.yaml")
        source_records.append(
            {
                "name": name,
                "version": manifest["version"],
                "status": manifest["status"],
                "runtime_activation": manifest["runtime_activation"],
                "sha256": package_digest(source),
            }
        )

    boundary = {
        "schema": "collective.host-projection.v1",
        "host": "openai-plugin",
        "plugin": PLUGIN_NAME,
        "version": PLUGIN_VERSION,
        "authority_class": "proposal_and_evidence_only",
        "authorizes_execution": False,
        "authorizes_external_writes": False,
        "authorizes_canonical_commit": False,
        "canonical_skills": source_records,
    }
    (destination / "COLLECTIVE_SOURCE.json").write_text(
        json.dumps(boundary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return boundary


def build_marketplace(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    marketplace = {
        "name": "collectiveos",
        "interface": {"displayName": "CollectiveOS"},
        "plugins": [
            {
                "name": PLUGIN_NAME,
                "source": {
                    "source": "local",
                    "path": "./plugins/collectiveos-core-preview",
                },
                "policy": {
                    "installation": "AVAILABLE",
                    "authentication": "ON_INSTALL",
                },
                "category": "Productivity",
            }
        ],
    }
    path.write_text(json.dumps(marketplace, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compile canonical CollectiveOS skills into an OpenAI portable plugin projection."
    )
    parser.add_argument("--output", type=Path, default=ROOT / "plugins" / PLUGIN_NAME)
    parser.add_argument(
        "--marketplace",
        type=Path,
        default=ROOT / ".agents" / "plugins" / "marketplace.json",
    )
    args = parser.parse_args()
    boundary = build_plugin(args.output)
    build_marketplace(args.marketplace)
    print(json.dumps(boundary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
