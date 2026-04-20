"""Root runner for the OIMS reference family.

Executes the living ISO-1B reference organism and reports
a top-level family run result.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ISO1B_DIR = ROOT / "iso-models" / "iso-1b"
if str(ISO1B_DIR) not in sys.path:
    sys.path.insert(0, str(ISO1B_DIR))

from runtime import run_iso1b  # type: ignore


def run() -> dict:
    result = run_iso1b("family conformance probe")
    family_result = {
        "family": "OIMS",
        "executed_tier": "ISO-1B",
        "status": "executed",
        "result": result,
    }
    print(json.dumps(family_result, indent=2))
    return family_result


if __name__ == "__main__":
    run()
