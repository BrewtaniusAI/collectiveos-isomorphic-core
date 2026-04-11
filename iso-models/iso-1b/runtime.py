"""ISO-1B runtime integration.

This file provides a simple execution wrapper for the ISO-1B model,
applies runtime behavioral contracts, and emits a tier-level conformance record.
"""

from __future__ import annotations

import json
import os
from typing import Dict, Any

from .model import ISO1BModel, ISO1BResponse
from .contract_enforcer import load_contract, enforce_contract
from .provenance import build_constraint_signals, build_proof_vault


CONFORMANCE_PATH = os.path.join(
    os.path.dirname(__file__), "conformance_record.jsonld"
)


def _apply_governance(
    response: ISO1BResponse,
    enforced_status: str,
) -> Dict[str, Any]:
    if enforced_status == "DIGITAL_APOPTOSIS":
        return {
            "status": "DIGITAL_APOPTOSIS",
            "lawful": False,
            "drift": 1.0,
            "output": "Execution collapsed: runtime behavioral contract violated.",
        }

    return {
        "status": response.status,
        "lawful": response.lawful,
        "drift": response.drift,
        "output": response.output,
    }


def run_iso1b(prompt: str = "test prompt") -> Dict[str, Any]:
    model = ISO1BModel()
    contract = load_contract()

    response = model.evaluate(prompt)
    enforced_status = enforce_contract(response, contract)
    governed = _apply_governance(response, enforced_status)

    record = {
        "@context": "https://oims.collective-osp.org/conformance/v1",
        "@type": "OIMSModelTierConformanceRecord",
        "model": model.model_name,
        "status": "executed",
        "contract_version": contract.get("version", "unknown"),
        "contract_model": contract.get("model", "unknown"),
        "enforced_status": enforced_status,
        "is_isomorphic": governed["lawful"] and governed["drift"] <= model.max_drift,
        "drift": governed["drift"],
        "output": governed["output"],
    }

    record["constraint_signals"] = build_constraint_signals(
        drift=governed["drift"],
        enforced_status=enforced_status,
        is_isomorphic=record["is_isomorphic"],
    )
    record["proof_vault"] = build_proof_vault(
        model=model.model_name,
        contract_version=record["contract_version"],
    )

    with open(CONFORMANCE_PATH, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2)

    return record


if __name__ == "__main__":
    result = run_iso1b()
    print("ISO-1B governed run complete")
    print(json.dumps(result, indent=2))
