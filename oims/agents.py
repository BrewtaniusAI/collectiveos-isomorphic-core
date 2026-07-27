"""Governed role bindings for OIMS and CollectiveOS."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .manifest import ROOT, FamilyManifest, load_manifest
from .proof import sha256_file, sha256_value

DEFAULT_AGENT_MANIFEST_PATH = ROOT / "AGENT_MANIFEST.json"


class AgentManifestError(ValueError):
    """Raised when an agent manifest or binding is invalid."""


@dataclass(frozen=True)
class AgentProfile:
    id: str
    display_name: str
    aliases: tuple[str, ...]
    tier: str
    purpose: str
    system_prompt: str

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> AgentProfile:
        try:
            aliases = tuple(str(item) for item in value.get("aliases", []))
            profile = cls(
                id=str(value["id"]),
                display_name=str(value["display_name"]),
                aliases=aliases,
                tier=str(value["tier"]),
                purpose=str(value["purpose"]),
                system_prompt=str(value["system_prompt"]),
            )
        except (KeyError, TypeError) as exc:
            raise AgentManifestError(f"invalid agent profile: {value!r}") from exc
        if not profile.id or not profile.system_prompt.strip():
            raise AgentManifestError("agent id and system_prompt must be nonempty")
        return profile

    def to_mapping(self, *, include_system_prompt: bool = False) -> dict[str, Any]:
        value: dict[str, Any] = {
            "id": self.id,
            "display_name": self.display_name,
            "aliases": list(self.aliases),
            "tier": self.tier,
            "purpose": self.purpose,
            "system_prompt_sha256": sha256_value(self.system_prompt),
        }
        if include_system_prompt:
            value["system_prompt"] = self.system_prompt
        return value


@dataclass(frozen=True)
class AgentRegistry:
    schema_version: int
    family: str
    activation_semantics: str
    autonomous_worker_claim: bool
    governance_route: tuple[str, ...]
    default_agent: str
    profiles: tuple[AgentProfile, ...]
    source_hash: str

    def resolve(self, name: str | None) -> AgentProfile:
        requested = (name or self.default_agent).casefold()
        for profile in self.profiles:
            names = {profile.id.casefold(), profile.display_name.casefold()}
            names.update(alias.casefold() for alias in profile.aliases)
            if requested in names:
                return profile
        choices = ", ".join(profile.id for profile in self.profiles)
        raise AgentManifestError(f"unknown agent {name!r}; choose one of: {choices}")

    def binding(self, profile: AgentProfile) -> dict[str, Any]:
        value = profile.to_mapping()
        value["agent_manifest_sha256"] = self.source_hash
        return value


def load_agent_registry(
    path: Path | str = DEFAULT_AGENT_MANIFEST_PATH,
    *,
    manifest: FamilyManifest | None = None,
) -> AgentRegistry:
    manifest = manifest or load_manifest()
    agent_path = Path(path)
    try:
        raw = json.loads(agent_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AgentManifestError(f"cannot load agent manifest {agent_path}: {exc}") from exc

    profiles = tuple(AgentProfile.from_mapping(item) for item in raw.get("profiles", []))
    if not profiles:
        raise AgentManifestError("agent manifest contains no profiles")
    if str(raw.get("family")) != manifest.family:
        raise AgentManifestError("agent manifest family does not match model manifest")
    if raw.get("activation_semantics") != "role_binding_only":
        raise AgentManifestError("activation_semantics must be role_binding_only")
    if raw.get("autonomous_worker_claim") is not False:
        raise AgentManifestError("autonomous_worker_claim must remain false")
    governance_route = tuple(str(item) for item in raw.get("governance_route", []))
    if governance_route != ("QC", "GATA", "GATA_PRIME"):
        raise AgentManifestError("governance_route must be QC -> GATA -> GATA_PRIME")

    tier_names = {tier.name for tier in manifest.tiers}
    if any(profile.tier not in tier_names for profile in profiles):
        raise AgentManifestError("every agent profile must bind to a declared model tier")

    lookup_names: list[str] = []
    for profile in profiles:
        lookup_names.extend([profile.id, profile.display_name, *profile.aliases])
    normalized = [item.casefold() for item in lookup_names]
    if len(normalized) != len(set(normalized)):
        raise AgentManifestError("agent ids, names, and aliases must be unique")

    registry = AgentRegistry(
        schema_version=int(raw["schema_version"]),
        family=str(raw["family"]),
        activation_semantics=str(raw["activation_semantics"]),
        autonomous_worker_claim=bool(raw["autonomous_worker_claim"]),
        governance_route=governance_route,
        default_agent=str(raw["default_agent"]),
        profiles=profiles,
        source_hash=sha256_file(agent_path),
    )
    registry.resolve(registry.default_agent)
    return registry
