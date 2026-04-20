"""Basic stress tests for ISO-1B."""

from __future__ import annotations

from .runtime import run_iso1b


def run_stress_suite():
    cases = [
        {"name": "empty", "prompt": ""},
        {"name": "normal", "prompt": "family conformance probe"},
    ]
    results = []
    for case in cases:
        results.append({"case": case["name"], "result": run_iso1b(case["prompt"])})
    return results


if __name__ == "__main__":
    import json
    print(json.dumps(run_stress_suite(), indent=2))
