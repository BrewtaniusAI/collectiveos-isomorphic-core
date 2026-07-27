"""Validated access to the pinned heterogeneous OIMS family manifest."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST_PATH = ROOT / "MODEL_MANIFEST.json"


class ManifestError(ValueError):
    """Raised when the family manifest is incomplete or internally inconsistent."""


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdef" for char in value)


@dataclass(frozen=True)
class WeightFileSpec:
    filename: str
    size: int
    sha256: str

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> WeightFileSpec:
        try:
            filename = str(value["filename"])
            size = int(value["size"])
            sha256 = str(value["sha256"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ManifestError(f"invalid weight file entry: {value!r}") from exc
        if not filename.endswith(".gguf"):
            raise ManifestError(f"weight file must be GGUF: {filename}")
        if size <= 0:
            raise ManifestError(f"weight file size must be positive: {filename}")
        if not _is_sha256(sha256):
            raise ManifestError(f"weight file must declare a lowercase SHA-256: {filename}")
        return cls(filename=filename, size=size, sha256=sha256)

    def to_mapping(self) -> dict[str, Any]:
        return {
            "filename": self.filename,
            "size": self.size,
            "sha256": self.sha256,
        }


@dataclass(frozen=True)
class TierSpec:
    name: str
    parameter_class: str
    capacity_class: str
    role: str
    provider: str
    architecture_family: str
    base_model_repo_id: str
    repo_id: str
    revision: str
    license: str
    quantization: str
    weight_files: tuple[WeightFileSpec, ...]
    context_length: int
    gpu_layers: int
    status: str
    conversion: str
    chat_system_mode: str

    @property
    def files(self) -> tuple[str, ...]:
        """Compatibility filename view used by the backend."""
        return tuple(item.filename for item in self.weight_files)

    @property
    def download_bytes(self) -> int:
        return sum(item.size for item in self.weight_files)

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> TierSpec:
        required = {
            "name",
            "parameter_class",
            "capacity_class",
            "role",
            "provider",
            "architecture_family",
            "base_model_repo_id",
            "repo_id",
            "revision",
            "license",
            "quantization",
            "files",
            "context_length",
            "gpu_layers",
            "status",
            "conversion",
            "chat_system_mode",
        }
        missing = sorted(required - value.keys())
        if missing:
            raise ManifestError(f"tier is missing required fields: {', '.join(missing)}")
        raw_files = value["files"]
        if not isinstance(raw_files, list) or not raw_files:
            raise ManifestError(f"{value['name']} must declare at least one GGUF file")
        files = tuple(WeightFileSpec.from_mapping(item) for item in raw_files)
        filenames = [item.filename for item in files]
        if len(filenames) != len(set(filenames)):
            raise ManifestError(f"{value['name']} contains duplicate GGUF filenames")
        revision = str(value["revision"])
        if len(revision) != 40 or any(char not in "0123456789abcdef" for char in revision):
            raise ManifestError(f"{value['name']} revision must be a pinned 40-character SHA")
        context_length = int(value["context_length"])
        if context_length <= 0:
            raise ManifestError(f"{value['name']} context_length must be positive")
        chat_system_mode = str(value["chat_system_mode"])
        if chat_system_mode not in {"native", "prepend-user"}:
            raise ManifestError(f"{value['name']} chat_system_mode must be native or prepend-user")
        return cls(
            name=str(value["name"]),
            parameter_class=str(value["parameter_class"]),
            capacity_class=str(value["capacity_class"]),
            role=str(value["role"]),
            provider=str(value["provider"]),
            architecture_family=str(value["architecture_family"]),
            base_model_repo_id=str(value["base_model_repo_id"]),
            repo_id=str(value["repo_id"]),
            revision=revision,
            license=str(value["license"]),
            quantization=str(value["quantization"]),
            weight_files=files,
            context_length=context_length,
            gpu_layers=int(value["gpu_layers"]),
            status=str(value["status"]),
            conversion=str(value["conversion"]),
            chat_system_mode=chat_system_mode,
        )

    def to_mapping(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "parameter_class": self.parameter_class,
            "capacity_class": self.capacity_class,
            "role": self.role,
            "provider": self.provider,
            "architecture_family": self.architecture_family,
            "base_model_repo_id": self.base_model_repo_id,
            "repo_id": self.repo_id,
            "revision": self.revision,
            "license": self.license,
            "quantization": self.quantization,
            "files": [item.to_mapping() for item in self.weight_files],
            "context_length": self.context_length,
            "gpu_layers": self.gpu_layers,
            "status": self.status,
            "conversion": self.conversion,
            "chat_system_mode": self.chat_system_mode,
        }


@dataclass(frozen=True)
class MeshSpec:
    name: str
    status: str
    strategy: str
    members: tuple[str, ...]

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> MeshSpec:
        try:
            return cls(
                name=str(value["name"]),
                status=str(value["status"]),
                strategy=str(value["strategy"]),
                members=tuple(str(item) for item in value["members"]),
            )
        except (KeyError, TypeError) as exc:
            raise ManifestError("manifest mesh declaration is incomplete") from exc

    def to_mapping(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "strategy": self.strategy,
            "members": list(self.members),
        }


@dataclass(frozen=True)
class FamilyManifest:
    schema_version: int
    family: str
    runtime: str
    shared_contract: str
    diversity_policy: str
    tiers: tuple[TierSpec, ...]
    mesh: MeshSpec

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
    if names != ["ISO-1B", "ISO-7B", "ISO-30B"]:
        raise ManifestError("manifest must declare the complete ISO-1B/ISO-7B/ISO-30B family")
    if int(raw.get("schema_version", 0)) != 3:
        raise ManifestError("model manifest schema_version must be 3")

    diversity_policy = str(raw.get("diversity_policy", ""))
    architecture_families = {tier.architecture_family for tier in tiers}
    providers = {tier.provider for tier in tiers}
    if diversity_policy == "heterogeneous-architecture-required":
        if len(architecture_families) != len(tiers):
            raise ManifestError("each tier must use a distinct architecture family")
        if len(providers) != len(tiers):
            raise ManifestError("each tier must use a distinct upstream provider")

    contract_path = ROOT / str(raw.get("shared_contract", ""))
    if not contract_path.is_file():
        raise ManifestError(f"shared contract does not exist: {contract_path}")

    mesh = MeshSpec.from_mapping(raw.get("mesh", {}))
    if mesh.name != "ISO-Mesh":
        raise ManifestError("mesh name must be ISO-Mesh")
    if mesh.members != tuple(names):
        raise ManifestError("mesh members must exactly match model tier order")

    return FamilyManifest(
        schema_version=int(raw["schema_version"]),
        family=str(raw["family"]),
        runtime=str(raw["runtime"]),
        shared_contract=str(raw["shared_contract"]),
        diversity_policy=diversity_policy,
        tiers=tiers,
        mesh=mesh,
    )
