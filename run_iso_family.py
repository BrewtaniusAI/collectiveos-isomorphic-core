"""Compatibility runner for all pinned OIMS model tiers."""

from __future__ import annotations

import argparse

from oims.runtime import print_json, run_family


def run(prompt: str = "family conformance probe") -> dict:
    result = run_family(prompt)
    print_json(result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt", default="family conformance probe")
    arguments = parser.parse_args()
    run(arguments.prompt)
