from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
ALLOWED_STATUS = {"draft", "experimental", "active", "deprecated"}
ALLOWED_EXTERNAL_ACTIONS = {"none", "approval_required"}
REQUIRED_MANIFEST_KEYS = {
    "name",
    "version",
    "status",
    "runtime_activation",
    "summary",
    "category",
    "triggers",
    "inputs",
    "outputs",
    "permissions",
    "invariants",
    "acceptance_checks",
}
REQUIRED_PACKAGE_FILES = ("SKILL.md", "skill.yaml", "tests/evals.yaml")


class SkillValidationError(ValueError):
    pass


@dataclass(frozen=True)
class SkillPackage:
    path: Path
    name: str
    version: str
    digest: str


def _load_yaml(path: Path) -> object:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise SkillValidationError(f"{path}: unreadable YAML: {exc}") from exc


def _require_string_list(value: object, field: str, manifest_path: Path) -> None:
    if (
        not isinstance(value, list)
        or not value
        or not all(isinstance(item, str) and item for item in value)
    ):
        raise SkillValidationError(f"{manifest_path}: {field} must be a non-empty list of strings")


def _validate_manifest(manifest: object, manifest_path: Path) -> dict[str, object]:
    if not isinstance(manifest, dict):
        raise SkillValidationError(f"{manifest_path}: manifest must be a mapping")

    missing = REQUIRED_MANIFEST_KEYS - set(manifest)
    if missing:
        raise SkillValidationError(f"{manifest_path}: missing keys: {sorted(missing)}")

    name = manifest["name"]
    version = manifest["version"]
    status = manifest["status"]
    runtime_activation = manifest["runtime_activation"]

    if not isinstance(name, str) or not NAME_RE.fullmatch(name):
        raise SkillValidationError(f"{manifest_path}: invalid skill name")
    if not isinstance(version, str) or not VERSION_RE.fullmatch(version):
        raise SkillValidationError(f"{manifest_path}: version must be semantic x.y.z")
    if not isinstance(status, str) or status not in ALLOWED_STATUS:
        raise SkillValidationError(f"{manifest_path}: unsupported status {status!r}")
    if not isinstance(runtime_activation, bool):
        raise SkillValidationError(f"{manifest_path}: runtime_activation must be boolean")
    if status == "draft" and runtime_activation:
        raise SkillValidationError(f"{manifest_path}: draft skills cannot be runtime-active")

    for field in ("triggers", "inputs", "outputs", "invariants", "acceptance_checks"):
        _require_string_list(manifest[field], field, manifest_path)

    permissions = manifest["permissions"]
    if not isinstance(permissions, dict) or set(permissions) != {
        "read",
        "write",
        "external_actions",
    }:
        raise SkillValidationError(
            f"{manifest_path}: permissions must declare exactly read/write/external_actions"
        )
    if not isinstance(permissions["read"], list) or not all(
        isinstance(item, str) and item for item in permissions["read"]
    ):
        raise SkillValidationError(f"{manifest_path}: permissions.read must be a list of strings")
    write = permissions["write"]
    if write != [] and write != "approval_required":
        raise SkillValidationError(
            f"{manifest_path}: permissions.write must be [] or approval_required"
        )
    external_actions = permissions["external_actions"]
    if not isinstance(external_actions, str) or external_actions not in ALLOWED_EXTERNAL_ACTIONS:
        raise SkillValidationError(f"{manifest_path}: invalid external_actions permission")

    return manifest


def _validate_evals(evals: object, eval_path: Path) -> None:
    if (
        not isinstance(evals, dict)
        or type(evals.get("version")) is not int
        or evals["version"] != 1
    ):
        raise SkillValidationError(f"{eval_path}: eval format version must be 1")
    cases = evals.get("cases")
    if not isinstance(cases, list) or not cases:
        raise SkillValidationError(f"{eval_path}: cases must be a non-empty list")
    ids: set[str] = set()
    for case in cases:
        if not isinstance(case, dict) or not isinstance(case.get("id"), str) or not case["id"]:
            raise SkillValidationError(f"{eval_path}: every case requires a non-empty string id")
        case_id = case["id"]
        if case_id in ids:
            raise SkillValidationError(f"{eval_path}: duplicate eval id {case_id!r}")
        ids.add(case_id)
        if not isinstance(case.get("prompt"), str) or not case["prompt"]:
            raise SkillValidationError(f"{eval_path}: {case_id}: prompt is required")
        for field in ("expect", "reject"):
            _require_string_list(case.get(field), f"{case_id}.{field}", eval_path)


def package_digest(package_dir: Path) -> str:
    digest = hashlib.sha256()
    for relative in REQUIRED_PACKAGE_FILES:
        path = package_dir / relative
        data = path.read_bytes()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(data)
        digest.update(b"\0")
    return digest.hexdigest()


def validate_package(package_dir: Path) -> SkillPackage:
    for relative in REQUIRED_PACKAGE_FILES:
        path = package_dir / relative
        if not path.is_file():
            raise SkillValidationError(f"{package_dir}: missing required file {relative}")

    manifest_path = package_dir / "skill.yaml"
    manifest = _validate_manifest(_load_yaml(manifest_path), manifest_path)
    if manifest["name"] != package_dir.name:
        raise SkillValidationError(
            f"{manifest_path}: manifest name must match package directory {package_dir.name!r}"
        )

    skill_md = (package_dir / "SKILL.md").read_text(encoding="utf-8")
    if not skill_md.strip():
        raise SkillValidationError(f"{package_dir / 'SKILL.md'}: file must not be empty")

    eval_path = package_dir / "tests/evals.yaml"
    _validate_evals(_load_yaml(eval_path), eval_path)

    return SkillPackage(
        path=package_dir,
        name=str(manifest["name"]),
        version=str(manifest["version"]),
        digest=package_digest(package_dir),
    )


def discover_packages(skills_dir: Path) -> list[Path]:
    return sorted(
        path for path in skills_dir.iterdir() if path.is_dir() and (path / "skill.yaml").is_file()
    )


def validate_registry(skills_dir: Path) -> list[SkillPackage]:
    packages = [validate_package(path) for path in discover_packages(skills_dir)]
    identities: set[tuple[str, str]] = set()
    for package in packages:
        identity = (package.name, package.version)
        if identity in identities:
            raise SkillValidationError(
                f"duplicate skill identity: {package.name}@{package.version}"
            )
        identities.add(identity)
    return packages


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate CollectiveOS skill packages")
    parser.add_argument("--skills-dir", type=Path, default=Path("skills"))
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()

    try:
        packages = validate_registry(args.skills_dir)
    except (OSError, SkillValidationError) as exc:
        parser.exit(1, f"skill validation failed: {exc}\n")

    result = [
        {"name": package.name, "version": package.version, "sha256": package.digest}
        for package in packages
    ]
    if args.as_json:
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    else:
        for item in result:
            print(f"{item['name']}@{item['version']} {item['sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
