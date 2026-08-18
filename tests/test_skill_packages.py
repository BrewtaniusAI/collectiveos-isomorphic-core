from __future__ import annotations

import copy
from pathlib import Path

import pytest
import yaml

from tools.validate_skills import SkillValidationError, validate_package, validate_registry

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"
STARTER_NAMES = {"collective-os-core", "iere", "gaces"}


def test_starter_skill_registry_validates() -> None:
    packages = validate_registry(SKILLS)
    assert {package.name for package in packages} == STARTER_NAMES
    assert all(len(package.digest) == 64 for package in packages)


def test_all_draft_skills_are_explicitly_non_active() -> None:
    for name in STARTER_NAMES:
        manifest = yaml.safe_load((SKILLS / name / "skill.yaml").read_text(encoding="utf-8"))
        assert manifest["status"] == "draft"
        assert manifest["runtime_activation"] is False


def test_package_digest_is_deterministic() -> None:
    first = validate_package(SKILLS / "collective-os-core")
    second = validate_package(SKILLS / "collective-os-core")
    assert first.digest == second.digest


def test_runtime_activation_fails_closed_for_draft(tmp_path: Path) -> None:
    source = SKILLS / "collective-os-core"
    target = tmp_path / "collective-os-core"
    (target / "tests").mkdir(parents=True)
    (target / "SKILL.md").write_bytes((source / "SKILL.md").read_bytes())
    (target / "tests/evals.yaml").write_bytes((source / "tests/evals.yaml").read_bytes())
    manifest = yaml.safe_load((source / "skill.yaml").read_text(encoding="utf-8"))
    manifest["runtime_activation"] = True
    (target / "skill.yaml").write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")

    with pytest.raises(SkillValidationError, match="draft skills cannot be runtime-active"):
        validate_package(target)


def test_undeclared_permission_key_is_rejected(tmp_path: Path) -> None:
    source = SKILLS / "gaces"
    target = tmp_path / "gaces"
    (target / "tests").mkdir(parents=True)
    (target / "SKILL.md").write_bytes((source / "SKILL.md").read_bytes())
    (target / "tests/evals.yaml").write_bytes((source / "tests/evals.yaml").read_bytes())
    manifest = copy.deepcopy(yaml.safe_load((source / "skill.yaml").read_text(encoding="utf-8")))
    manifest["permissions"]["credential_write"] = "approval_required"
    (target / "skill.yaml").write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")

    with pytest.raises(SkillValidationError, match="permissions must declare exactly"):
        validate_package(target)
