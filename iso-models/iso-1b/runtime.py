"""Legacy import surface for the package-based ISO-1B runtime."""

from oims.runtime import run_tier


def run_iso1b(prompt: object = "test prompt") -> dict:
    return run_tier("ISO-1B", prompt)
