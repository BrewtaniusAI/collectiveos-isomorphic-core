from __future__ import annotations

from typing import Any

_REQUIRED_FALSE_AUTHORITY = (
    "authorizes_execution",
    "authorizes_external_writes",
    "authorizes_canonical_commit",
    "authorizes_governance_promotion",
)
_ALLOWED_KINDS = {"procedure", "actuator", "verifier"}
_ALLOWED_LOCALITY = {"local", "remote", "hybrid"}
_ALLOWED_COST_CLASS = {"free", "metered", "unknown"}
_FORBIDDEN_METADATA_KEYS = {
    "account_id",
    "user_id",
    "device_id",
    "machine_id",
    "machine_path",
    "local_path",
    "token",
    "api_token",
    "api_key",
    "secret",
    "password",
    "credential",
    "credentials",
    "signed_url",
    "balance",
}


def _forbidden_metadata_keys(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).strip().lower()
            if normalized in _FORBIDDEN_METADATA_KEYS:
                found.add(normalized)
            found.update(_forbidden_metadata_keys(child))
    elif isinstance(value, list):
        for child in value:
            found.update(_forbidden_metadata_keys(child))
    return found


def validate_inventory(inventory: dict[str, Any]) -> list[str]:
    violations: list[str] = []

    if inventory.get("schema") != "collective.capability-inventory.v1":
        violations.append("SCHEMA")
    if inventory.get("status") != "DECLARATIVE_NON_AUTHORIZING":
        violations.append("STATUS")

    authority = inventory.get("authority")
    if not isinstance(authority, dict):
        violations.append("AUTHORITY")
    else:
        if authority.get("discovery_is_advisory") is not True:
            violations.append("DISCOVERY_AUTHORITY")
        for key in _REQUIRED_FALSE_AUTHORITY:
            if authority.get(key) is not False:
                violations.append(f"AUTHORITY:{key}")

    capabilities = inventory.get("capabilities")
    if not isinstance(capabilities, list):
        violations.append("CAPABILITIES")
        return violations

    seen: set[str] = set()
    for index, item in enumerate(capabilities):
        if not isinstance(item, dict):
            violations.append(f"CAPABILITY:{index}")
            continue
        capability_id = item.get("capability_id")
        if not isinstance(capability_id, str) or not capability_id:
            violations.append(f"CAPABILITY_ID:{index}")
            continue
        if capability_id in seen:
            violations.append(f"DUPLICATE_CAPABILITY_ID:{capability_id}")
        seen.add(capability_id)

        if item.get("kind") not in _ALLOWED_KINDS:
            violations.append(f"KIND:{capability_id}")
        if item.get("locality") not in _ALLOWED_LOCALITY:
            violations.append(f"LOCALITY:{capability_id}")
        if item.get("cost_class") not in _ALLOWED_COST_CLASS:
            violations.append(f"COST_CLASS:{capability_id}")
        if not isinstance(item.get("provider"), str) or not item["provider"]:
            violations.append(f"PROVIDER:{capability_id}")
        if not isinstance(item.get("available"), bool):
            violations.append(f"AVAILABLE:{capability_id}")
        if not isinstance(item.get("connected"), bool):
            violations.append(f"CONNECTED:{capability_id}")
        if not isinstance(item.get("connection_required"), bool):
            violations.append(f"CONNECTION_REQUIRED:{capability_id}")

    for key in sorted(_forbidden_metadata_keys(inventory)):
        violations.append(f"FORBIDDEN_METADATA_KEY:{key}")

    return violations


def available_capability_ids(inventory: dict[str, Any]) -> set[str]:
    if validate_inventory(inventory):
        return set()

    available: set[str] = set()
    for item in inventory["capabilities"]:
        if item["available"] is not True:
            continue
        if item["connection_required"] and item["connected"] is not True:
            continue
        available.add(item["capability_id"])
    return available
