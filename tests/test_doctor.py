from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from oims.doctor import run_diagnostics
from oims.manifest import load_manifest


class DoctorTests(unittest.TestCase):
    def test_missing_weights_are_not_run_ready(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = run_diagnostics(load_manifest(), Path(directory) / "weights")
            self.assertFalse(result["weights_ready"])
            self.assertFalse(result["ready_for_family_run"])
            self.assertEqual(3, len(result["tiers"]))


if __name__ == "__main__":
    unittest.main()
