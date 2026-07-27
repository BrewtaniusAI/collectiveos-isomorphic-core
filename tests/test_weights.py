from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from oims.manifest import load_manifest
from oims.proof import atomic_write_json, sha256_file
from oims.weights import inspect_tier


class WeightTests(unittest.TestCase):
    def test_missing_weights_report_is_complete_false(self) -> None:
        manifest = load_manifest()
        with tempfile.TemporaryDirectory() as directory:
            for tier in manifest.tiers:
                status = inspect_tier(tier, Path(directory), compute_hashes=False)
                self.assertFalse(status["complete"])
                self.assertEqual(len(tier.files), len(status["files"]))

    def test_fast_check_does_not_claim_hash_verification(self) -> None:
        tier = load_manifest().tier("ISO-1B")
        with tempfile.TemporaryDirectory() as directory:
            tier_dir = Path(directory) / tier.name
            tier_dir.mkdir()
            weight = tier_dir / tier.files[0]
            weight.write_bytes(b"test-weight")
            atomic_write_json(
                tier_dir / "weights.lock.json",
                {
                    "files": [
                        {
                            "filename": weight.name,
                            "size": weight.stat().st_size,
                            "sha256": sha256_file(weight),
                        }
                    ]
                },
            )
            fast = inspect_tier(tier, Path(directory), compute_hashes=False)
            full = inspect_tier(tier, Path(directory), compute_hashes=True)
            self.assertTrue(fast["complete"])
            self.assertTrue(fast["lock_present"])
            self.assertTrue(fast["size_verified"])
            self.assertFalse(fast["hash_verified"])
            self.assertTrue(full["hash_verified"])


if __name__ == "__main__":
    unittest.main()
