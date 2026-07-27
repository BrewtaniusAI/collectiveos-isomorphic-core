"""Legacy executable smoke entrypoint for ISO-1B.

The assertive suite lives under tests/ and runs with unittest or pytest.
"""

from __future__ import annotations

from oims.runtime import fixture_backend_factory, run_tier


def run_stress_suite():
    cases = [
        {"name": "empty", "prompt": ""},
        {"name": "normal", "prompt": "family conformance probe"},
    ]
    results = []
    for case in cases:
        results.append(
            {
                "case": case["name"],
                "result": run_tier(
                    "ISO-1B",
                    case["prompt"],
                    backend_factory=fixture_backend_factory,
                ),
            }
        )
    return results


if __name__ == "__main__":
    import json

    print(json.dumps(run_stress_suite(), indent=2))
