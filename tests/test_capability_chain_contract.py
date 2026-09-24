from __future__ import annotations

import json
from pathlib import Path

from tools.validate_capability_chain import validate_chain

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "contracts" / "capability-chain.v1.schema.json"
EXAMPLE = ROOT / "examples" / "meshy-game-studio-capability-chain.v1.json"


def test_live_proof_chain_is_contiguous_and_non_authorizing() -> None:
    chain = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    assert validate_chain(chain) == []
    assert chain["status"] == "DECLARATIVE_NON_AUTHORIZING"
    assert chain["authority"]["composition_rule"] == (
        "INTERSECTION_ACROSS_ALL_LINKS_HOST_AND_POLICY"
    )
    assert chain["authority"]["authorizes_canonical_commit"] is False


def test_chain_requires_artifact_continuity() -> None:
    chain = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    chain["links"][1]["input_artifact"] = "wrong-artifact"
    assert "ARTIFACT_DISCONTINUITY:mesh-to-web" in validate_chain(chain)


def test_chain_rejects_missing_verifier_gate() -> None:
    chain = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    chain["links"][0]["verification_required"] = False
    assert "VERIFICATION_REQUIRED:meshy-build" in validate_chain(chain)


def test_chain_schema_keeps_authority_fail_closed() -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    authority = schema["properties"]["authority"]["properties"]
    assert authority["authorizes_execution"]["const"] is False
    assert authority["authorizes_external_writes"]["const"] is False
    assert authority["authorizes_canonical_commit"]["const"] is False
    assert authority["authorizes_governance_promotion"]["const"] is False
