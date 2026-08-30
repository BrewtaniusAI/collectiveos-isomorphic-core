from __future__ import annotations

import copy
import shutil
from pathlib import Path

import pytest
import yaml

from tools.validate_skills import SkillValidationError, validate_package, validate_registry

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"
STARTER_NAMES = {"collective-os-core", "iere", "gaces"}


def copy_package(name: str, tmp_path: Path) -> Path:
    target = tmp_path / name
    shutil.copytree(SKILLS / name, target)
    return target


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


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("status", [], "unsupported status"),
        ("external_actions", [], "invalid external_actions permission"),
    ],
)
def test_unhashable_enum_values_raise_controlled_errors(
    tmp_path: Path,
    field: str,
    value: object,
    error: str,
) -> None:
    target = copy_package("gaces", tmp_path)
    manifest_path = target / "skill.yaml"
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    if field == "status":
        manifest[field] = value
    else:
        manifest["permissions"][field] = value
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")

    with pytest.raises(SkillValidationError, match=error):
        validate_package(target)


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("version", True, "eval format version must be 1"),
        ("id", "", "every case requires a non-empty string id"),
    ],
)
def test_malformed_eval_scalars_are_rejected(
    tmp_path: Path,
    field: str,
    value: object,
    error: str,
) -> None:
    target = copy_package("gaces", tmp_path)
    eval_path = target / "tests" / "evals.yaml"
    evals = yaml.safe_load(eval_path.read_text(encoding="utf-8"))
    if field == "version":
        evals[field] = value
    else:
        evals["cases"][0][field] = value
    eval_path.write_text(yaml.safe_dump(evals, sort_keys=False), encoding="utf-8")

    with pytest.raises(SkillValidationError, match=error):
        validate_package(target)
