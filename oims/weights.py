"""Download, inventory, and verify pinned local GGUF weight files."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .manifest import FamilyManifest, TierSpec
from .proof import atomic_write_json, sha256_file, utc_now


class WeightError(RuntimeError):
    """Raised when weight download or verification cannot complete."""


@dataclass(frozen=True)
class WeightFileStatus:
    filename: str
    path: str
    exists: bool
    size: int | None
    sha256: str | None

    def to_mapping(self) -> dict[str, Any]:
        return {
            "filename": self.filename,
            "path": self.path,
            "exists": self.exists,
            "size": self.size,
            "sha256": self.sha256,
        }


def selected_tiers(manifest: FamilyManifest, tier: str) -> tuple[TierSpec, ...]:
    if tier.lower() == "all":
        return manifest.tiers
    return (manifest.tier(tier),)


def inspect_tier(
    spec: TierSpec,
    weights_root: Path,
    *,
    compute_hashes: bool,
) -> dict[str, Any]:
    tier_dir = weights_root / spec.name
    lock_path = tier_dir / "weights.lock.json"
    locked: dict[str, dict[str, Any]] = {}
    lock_metadata: dict[str, Any] = {}
    if lock_path.is_file():
        try:
            lock = json.loads(lock_path.read_text(encoding="utf-8"))
            lock_metadata = lock
            locked = {
                str(item["filename"]): item
                for item in lock.get("files", [])
                if isinstance(item, dict) and "filename" in item
            }
        except (OSError, json.JSONDecodeError, TypeError):
            locked = {}

    files: list[WeightFileStatus] = []
    expected = {item.filename: item for item in spec.weight_files}
    for file_spec in spec.weight_files:
        filename = file_spec.filename
        path = tier_dir / filename
        exists = path.is_file()
        size = path.stat().st_size if exists else None
        digest: str | None = None
        if exists and compute_hashes:
            digest = sha256_file(path)
        files.append(
            WeightFileStatus(
                filename=filename,
                path=str(path),
                exists=exists,
                size=size,
                sha256=digest,
            )
        )

    complete = all(item.exists for item in files)
    lock_present = bool(locked) and all(item.filename in locked for item in files)
    size_verified = complete and all(item.size == expected[item.filename].size for item in files)
    lock_matches_manifest = (
        lock_present
        and lock_metadata.get("repo_id") == spec.repo_id
        and lock_metadata.get("revision") == spec.revision
        and all(
            locked[item.filename].get("size") == expected[item.filename].size
            and locked[item.filename].get("sha256") == expected[item.filename].sha256
            for item in files
        )
    )
    hash_verified = False
    if complete and compute_hashes:
        hash_verified = all(
            item.sha256 is not None
            and item.sha256 == expected[item.filename].sha256
            and item.size == expected[item.filename].size
            for item in files
        )

    return {
        "tier": spec.name,
        "repo_id": spec.repo_id,
        "revision": spec.revision,
        "quantization": spec.quantization,
        "complete": complete,
        "lock_present": lock_present,
        "lock_matches_manifest": lock_matches_manifest,
        "size_verified": size_verified,
        "hash_verified": hash_verified,
        "expected_download_bytes": spec.download_bytes,
        "files": [item.to_mapping() for item in files],
    }


def pull_tier(spec: TierSpec, weights_root: Path) -> dict[str, Any]:
    try:
        from huggingface_hub import hf_hub_download
    except ImportError as exc:
        raise WeightError(
            "huggingface-hub is not installed. Run: pip install -e '.[weights]'"
        ) from exc

    tier_dir = weights_root / spec.name
    tier_dir.mkdir(parents=True, exist_ok=True)
    downloaded: list[Path] = []
    for filename in spec.files:
        try:
            local_path = hf_hub_download(
                repo_id=spec.repo_id,
                filename=filename,
                revision=spec.revision,
                local_dir=tier_dir,
            )
        except Exception as exc:
            raise WeightError(f"failed to download {spec.repo_id}/{filename}: {exc}") from exc
        downloaded.append(Path(local_path))

    inventory = []
    expected = {item.filename: item for item in spec.weight_files}
    for path in downloaded:
        file_spec = expected[path.name]
        actual = {
            "filename": path.name,
            "size": path.stat().st_size,
            "sha256": sha256_file(path),
        }
        if actual["size"] != file_spec.size or actual["sha256"] != file_spec.sha256:
            raise WeightError(
                f"{spec.name} upstream identity mismatch for {path.name}: "
                "downloaded bytes do not match MODEL_MANIFEST.json"
            )
        inventory.append(actual)
    lock = {
        "schema_version": 1,
        "tier": spec.name,
        "repo_id": spec.repo_id,
        "revision": spec.revision,
        "quantization": spec.quantization,
        "license": spec.license,
        "created_at": utc_now(),
        "files": inventory,
    }
    atomic_write_json(tier_dir / "weights.lock.json", lock)
    status = inspect_tier(spec, weights_root, compute_hashes=False)
    status["hash_verified"] = True
    status["verification"] = "sha256-matched-pinned-upstream-identity"
    return status


def pull_weights(
    specs: Iterable[TierSpec],
    weights_root: Path,
) -> list[dict[str, Any]]:
    return [pull_tier(spec, weights_root) for spec in specs]
