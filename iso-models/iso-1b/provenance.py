"""ISO-1B provenance helpers.

Builds typed constraint-signal provenance blocks for tier-level conformance records.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List


def build_constraint_signals(*, drift: float, enforced_status: str, is_isomorphic: bool) -> List[Dict[str, Any]]:
    return [
        {
            "type": "Functional",
            "constraint": "Runtime Behavioral Contract",
            "condition": "drift <= 0.05 and lawful status preserved",
            "verification": "contract_enforcer",
            "satisfied": bool(is_isomorphic),
        },
        {
            "type": "Cybernetic",
            "constraint": "Governance-over-execution",
            "condition": "enforced_status is computed before artifact emission",
            "verification": "runtime enforcement path",
            "satisfied": enforced_status in ["LAWFUL", "IDLE", "DIGITAL_APOPTOSIS"],
        },
        {
            "type": "Functional",
            "constraint": "Collapse on hard violation",
            "condition": "forced violations map to DIGITAL_APOPTOSIS",
            "verification": "contract policy mapping",
            "satisfied": enforced_status != "DIGITAL_APOPTOSIS" or drift >= 1.0,
        },
    ]


def build_proof_vault(*, model: str, contract_version: str) -> Dict[str, Any]:
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "lineage": "pending-hash",
        "governance": "QC→GATA→GATA PRIME",
        "model": model,
        "contract_version": contract_version,
    }
