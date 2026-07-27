from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from oims.proof import verify_sealed_record
from oims.runtime import fixture_backend_factory, run_family, run_tier


class RuntimeTests(unittest.TestCase):
    def test_fixture_family_is_structurally_conformant_but_not_weight_verified(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report = run_family(
                "family conformance probe",
                backend_factory=fixture_backend_factory,
                artifacts_dir=Path(directory),
            )
            self.assertEqual("CONFORMANT", report["status"])
            self.assertTrue(report["runtime_isomorphic"])
            self.assertFalse(report["weight_execution_verified"])
            self.assertEqual("TEST_OR_INCOMPLETE", report["evidence_class"])
            self.assertEqual(["ISO-1B", "ISO-7B", "ISO-30B"], report["executed_tiers"])
            self.assertTrue(verify_sealed_record(report))
            saved = json.loads(
                (Path(directory) / "conformance_report.jsonld").read_text(encoding="utf-8")
            )
            self.assertEqual(report["record_sha256"], saved["record_sha256"])

    def test_hard_preflight_never_calls_backend(self) -> None:
        calls = []

        def forbidden_factory(spec):
            calls.append(spec.name)
            raise AssertionError("backend must not be called")

        with tempfile.TemporaryDirectory() as directory:
            record = run_tier(
                "ISO-1B",
                object(),
                backend_factory=forbidden_factory,
                artifacts_dir=Path(directory),
            )
            self.assertEqual([], calls)
            self.assertEqual("DIGITAL_APOPTOSIS", record["status"])

    def test_record_hash_detects_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            record = run_tier(
                "ISO-1B",
                "probe",
                backend_factory=fixture_backend_factory,
                artifacts_dir=Path(directory),
            )
            self.assertTrue(verify_sealed_record(record))
            record["output"] = "tampered"
            self.assertFalse(verify_sealed_record(record))

    def test_real_backend_fails_closed_when_weights_are_missing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            record = run_tier(
                "ISO-1B",
                "probe",
                weights_dir=root / "weights",
                artifacts_dir=root / "artifacts",
            )
            self.assertEqual("BACKEND_UNAVAILABLE", record["status"])
            self.assertFalse(record["weight_execution_verified"])
            self.assertIn("weights are incomplete", record["output"])


if __name__ == "__main__":
    unittest.main()
