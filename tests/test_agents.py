from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from oims.agents import load_agent_registry
from oims.backends import DeterministicFixtureBackend
from oims.collective import run_collective_request
from oims.verify import verify_artifact


class AgentTests(unittest.TestCase):
    def test_collective_aliases_bind_to_declared_roles(self) -> None:
        registry = load_agent_registry()
        self.assertEqual("ISO-1B", registry.resolve("Syn").tier)
        self.assertEqual("ISO-7B", registry.resolve("Rabbit").tier)
        self.assertEqual("ISO-7B", registry.resolve("Muse").tier)
        self.assertEqual("ISO-30B", registry.resolve("Giles").tier)
        self.assertEqual("ISO-30B", registry.resolve("Cypher").tier)
        self.assertEqual("ISO-30B", registry.resolve("Locke").tier)
        self.assertEqual("role_binding_only", registry.activation_semantics)
        self.assertFalse(registry.autonomous_worker_claim)
        self.assertEqual(("QC", "GATA", "GATA_PRIME"), registry.governance_route)

    def test_collective_fixture_response_is_linked_and_verifiable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = run_collective_request(
                {
                    "request_id": "test-request",
                    "agent": "Giles",
                    "prompt": "produce a bounded strategy",
                    "max_tokens": 64,
                },
                backend_factory=lambda spec, profile: DeterministicFixtureBackend(spec),
                artifacts_dir=Path(directory),
            )
            self.assertEqual("giles-strategist", result["agent_binding"]["id"])
            self.assertEqual("ISO-30B", result["result"]["model"])
            self.assertFalse(result["autonomous_worker_claim"])
            self.assertEqual(["QC", "GATA", "GATA_PRIME"], result["governance_route"])
            self.assertTrue(verify_artifact(result)["valid"])

    def test_collective_tamper_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = run_collective_request(
                {"agent": "Syn", "prompt": "intake"},
                backend_factory=lambda spec, profile: DeterministicFixtureBackend(spec),
                artifacts_dir=Path(directory),
            )
            result["agent_binding"]["tier"] = "ISO-30B"
            self.assertFalse(verify_artifact(result)["valid"])


if __name__ == "__main__":
    unittest.main()
