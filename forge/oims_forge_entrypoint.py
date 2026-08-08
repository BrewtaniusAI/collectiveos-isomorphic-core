"""Verify the installed Forge controller before importing any project code."""

from __future__ import annotations

import hashlib
import importlib.util
import os
import sys
from pathlib import Path

ATTESTATION_PATH = Path("/usr/local/share/oims-forge/source.attestation")


def _is_revision(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 40
        and all(character in "0123456789abcdef" for character in value)
    )


def _is_digest(value: object) -> bool:
    return (
        isinstance(value, str)
        and value.startswith("sha256:")
        and len(value) == 71
        and all(character in "0123456789abcdef" for character in value[7:])
    )


def package_digest(package_root: Path) -> str | None:
    try:
        root = package_root.resolve(strict=True)
        paths = sorted(root.rglob("*"), key=lambda path: path.relative_to(root).as_posix())
        digest = hashlib.sha256()
        for path in paths:
            relative = path.relative_to(root)
            if "__pycache__" in relative.parts or path.is_symlink():
                return None
            if path.is_dir():
                continue
            if not path.is_file():
                return None
            name = relative.as_posix().encode("utf-8")
            content = path.read_bytes()
            for field in (name, content):
                digest.update(len(field).to_bytes(8, "big"))
                digest.update(field)
    except (OSError, RuntimeError, UnicodeError):
        return None
    return "sha256:" + digest.hexdigest()


def installed_package_root() -> Path | None:
    try:
        specification = importlib.util.find_spec("oims")
        locations = tuple(specification.submodule_search_locations or ()) if specification else ()
        if len(locations) != 1:
            return None
        root = Path(locations[0]).resolve(strict=True)
        interpreter_prefix = Path(sys.prefix).resolve(strict=True)
    except (OSError, RuntimeError, TypeError, ValueError):
        return None
    workspace = Path("/workspace")
    if (
        sys.flags.isolated != 1
        or interpreter_prefix not in root.parents
        or workspace in root.parents
    ):
        return None
    return root


def _read_values(path: Path) -> dict[str, str] | None:
    try:
        if path.stat().st_size > 256:
            return None
        lines = path.read_text(encoding="ascii").splitlines()
    except (OSError, UnicodeDecodeError):
        return None
    values: dict[str, str] = {}
    for line in lines:
        key, separator, value = line.partition("=")
        if not separator or key in values:
            return None
        values[key] = value
    return values


def verify_installed_package(
    attestation_path: Path = ATTESTATION_PATH,
    package_root: Path | None = None,
) -> tuple[str, ...]:
    values = _read_values(attestation_path)
    if values is None or set(values) != {"commit", "tree", "package_sha256"}:
        return ("Forge source attestation is missing or malformed",)
    if not _is_revision(values["commit"]) or not _is_revision(values["tree"]):
        return ("Forge source attestation revisions are malformed",)
    if not _is_digest(values["package_sha256"]):
        return ("Forge installed-package attestation is malformed",)
    root = package_root if package_root is not None else installed_package_root()
    if root is None:
        return ("Forge installed package is not isolated from runtime shadowing",)
    observed = package_digest(root)
    if observed != values["package_sha256"]:
        return ("Forge installed package does not match its build attestation",)
    return ()


def seal_attestation(attestation_path: Path = ATTESTATION_PATH) -> int:
    if not hasattr(os, "geteuid") or os.geteuid() != 0:
        print("Forge attestation sealing requires the image-build root user", file=sys.stderr)
        return 70
    values = _read_values(attestation_path)
    if values is None or set(values) != {"commit", "tree"}:
        print("Forge source attestation is missing or malformed", file=sys.stderr)
        return 70
    if not _is_revision(values["commit"]) or not _is_revision(values["tree"]):
        print("Forge source attestation revisions are malformed", file=sys.stderr)
        return 70
    root = installed_package_root()
    observed = package_digest(root) if root is not None else None
    if observed is None:
        print("Forge installed package cannot be attested", file=sys.stderr)
        return 70
    try:
        with attestation_path.open("a", encoding="ascii", newline="\n") as handle:
            handle.write(f"package_sha256={observed}\n")
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as exc:
        print(f"cannot seal Forge installed-package attestation: {exc}", file=sys.stderr)
        return 70
    return 0


def main(arguments: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if arguments is None else arguments)
    if argv == ["--seal-attestation"]:
        return seal_attestation()
    errors = verify_installed_package()
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 70
    os.execv(sys.executable, [sys.executable, "-I", "-m", "oims", *argv])
    return 70


if __name__ == "__main__":
    raise SystemExit(main())
