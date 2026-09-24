from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "contracts" / "capability-link.v1.schema.json"
EXAMPLE = ROOT / "examples" / "meshy-capability-link.v1.json"


def test_capability_link_example_is_non_authorizing() -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    example = json.loads(EXAMPLE.read_text(encoding="utf-8"))

    assert example["schema"] == "collective.capability-link.v1"
    assert example["status"] == "DECLARATIVE_NON_AUTHORIZING"
    assert example["skill"]["role"] == "procedure"
    assert example["verification"]["required"] is True
    assert example["verification"]["decision_required_before_promotion"] is True

    authority = example["authority"]
    assert authority["composition_rule"] == "INTERSECTION_OF_SKILL_ACTUATOR_HOST_AND_POLICY"
    assert authority["authorizes_execution"] is False
    assert authority["authorizes_external_writes"] is False
    assert authority["authorizes_canonical_commit"] is False
    assert authority["authorizes_governance_promotion"] is False

    allowed = schema["properties"]["artifact_flow"]["properties"]["output_authority"]["enum"]
    assert example["artifact_flow"]["output_authority"] in allowed


def test_capability_link_schema_fixes_fail_closed_authority() -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    authority = schema["properties"]["authority"]["properties"]

    assert authority["composition_rule"]["const"] == (
        "INTERSECTION_OF_SKILL_ACTUATOR_HOST_AND_POLICY"
    )
    assert authority["authorizes_execution"]["const"] is False
    assert authority["authorizes_external_writes"]["const"] is False
    assert authority["authorizes_canonical_commit"]["const"] is False
    assert authority["authorizes_governance_promotion"]["const"] is False
