"""Validated access to the pinned OIMS model-family manifest."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST_PATH = ROOT / "MODEL_MANIFEST.json"


class ManifestError(ValueError):
    """Raised when the family manifest is incomplete or internally inconsistent."""


@dataclass(frozen=True)
class TierSpec:
    name: str
    parameter_class: str
    repo_id: str
    revision: str
    license: str
    quantization: str
    files: tuple[str, ...]
    context_length: int
    gpu_layers: int
    download_bytes_approx: int
    status: str

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> TierSpec:
        required = {
            "name",
            "parameter_class",
            "repo_id",
            "revision",
            "license",
            "quantization",
            "files",
            "context_length",
            "gpu_layers",
            "download_bytes_approx",
            "status",
        }
        missing = sorted(required - value.keys())
        if missing:
            raise ManifestError(f"tier is missing required fields: {', '.join(missing)}")
        files = tuple(str(item) for item in value["files"])
        if not files or any(not item.endswith(".gguf") for item in files):
            raise ManifestError(f"{value['name']} must declare at least one GGUF file")
        revision = str(value["revision"])
        if len(revision) != 40 or any(char not in "0123456789abcdef" for char in revision):
            raise ManifestError(f"{value['name']} revision must be a pinned 40-character SHA")
        return cls(
            name=str(value["name"]),
            parameter_class=str(value["parameter_class"]),
            repo_id=str(value["repo_id"]),
            revision=revision,
            license=str(value["license"]),
            quantization=str(value["quantization"]),
            files=files,
            context_length=int(value["context_length"]),
            gpu_layers=int(value["gpu_layers"]),
            download_bytes_approx=int(value["download_bytes_approx"]),
            status=str(value["status"]),
        )

    def to_mapping(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "parameter_class": self.parameter_class,
            "repo_id": self.repo_id,
            "revision": self.revision,
            "license": self.license,
            "quantization": self.quantization,
            "files": list(self.files),
            "context_length": self.context_length,
            "gpu_layers": self.gpu_layers,
            "download_bytes_approx": self.download_bytes_approx,
            "status": self.status,
        }


@dataclass(frozen=True)
class FamilyManifest:
    schema_version: int
    family: str
    runtime: str
    shared_contract: str
    tiers: tuple[TierSpec, ...]

    def tier(self, name: str) -> TierSpec:
        normalized = name.upper()
        for tier in self.tiers:
            if tier.name.upper() == normalized:
                return tier
        choices = ", ".join(tier.name for tier in self.tiers)
        raise ManifestError(f"unknown tier {name!r}; choose one of: {choices}")


def load_manifest(path: Path | str = DEFAULT_MANIFEST_PATH) -> FamilyManifest:
    manifest_path = Path(path)
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ManifestError(f"cannot load model manifest {manifest_path}: {exc}") from exc

    tiers = tuple(TierSpec.from_mapping(item) for item in raw.get("models", []))
    if not tiers:
        raise ManifestError("model manifest contains no tiers")
    names = [tier.name for tier in tiers]
    if len(names) != len(set(names)):
        raise ManifestError("model manifest contains duplicate tier names")

    contract_path = ROOT / str(raw.get("shared_contract", ""))
    if not contract_path.is_file():
        raise ManifestError(f"shared contract does not exist: {contract_path}")

    return FamilyManifest(
        schema_version=int(raw["schema_version"]),
        family=str(raw["family"]),
        runtime=str(raw["runtime"]),
        shared_contract=str(raw["shared_contract"]),
        tiers=tiers,
    )
