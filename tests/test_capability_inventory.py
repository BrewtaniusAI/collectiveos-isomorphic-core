from __future__ import annotations

import copy
import json
from pathlib import Path

from tools.capability_inventory import available_capability_ids, validate_inventory

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "examples" / "capability-inventory.sanitized.v1.json"


def _inventory() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_sanitized_inventory_is_valid() -> None:
    assert validate_inventory(_inventory()) == []


def test_unavailable_or_disconnected_required_capabilities_are_excluded() -> None:
    inventory = _inventory()
    inventory["capabilities"][0]["available"] = False
    inventory["capabilities"][1]["connected"] = False

    available = available_capability_ids(inventory)

    assert inventory["capabilities"][0]["capability_id"] not in available
    assert inventory["capabilities"][1]["capability_id"] not in available


def test_inventory_rejects_authorizing_root() -> None:
    inventory = _inventory()
    inventory["authority"]["authorizes_execution"] = True
    assert "AUTHORITY:authorizes_execution" in validate_inventory(inventory)


def test_inventory_rejects_sensitive_metadata_keys_recursively() -> None:
    inventory = copy.deepcopy(_inventory())
    inventory["capabilities"][0]["metadata"] = {
        "device_id": "forbidden",
        "nested": {"api_token": "forbidden"},
    }

    violations = validate_inventory(inventory)

    assert "FORBIDDEN_METADATA_KEY:device_id" in violations
    assert "FORBIDDEN_METADATA_KEY:api_token" in violations
