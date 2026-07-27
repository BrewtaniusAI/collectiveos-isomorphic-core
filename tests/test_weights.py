from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from oims.manifest import WeightFileSpec, load_manifest
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
        original = load_manifest().tier("ISO-1B")
        content = b"test-weight"
        digest = __import__("hashlib").sha256(content).hexdigest()
        tier = replace(
            original,
            weight_files=(
                WeightFileSpec(
                    filename=original.files[0],
                    size=len(content),
                    sha256=digest,
                ),
            ),
        )
        with tempfile.TemporaryDirectory() as directory:
            tier_dir = Path(directory) / tier.name
            tier_dir.mkdir()
            weight = tier_dir / tier.files[0]
            weight.write_bytes(content)
            atomic_write_json(
                tier_dir / "weights.lock.json",
                {
                    "repo_id": tier.repo_id,
                    "revision": tier.revision,
                    "files": [
                        {
                            "filename": weight.name,
                            "size": weight.stat().st_size,
                            "sha256": sha256_file(weight),
                        }
                    ],
                },
            )
            fast = inspect_tier(tier, Path(directory), compute_hashes=False)
            full = inspect_tier(tier, Path(directory), compute_hashes=True)
            self.assertTrue(fast["complete"])
            self.assertTrue(fast["lock_present"])
            self.assertTrue(fast["lock_matches_manifest"])
            self.assertTrue(fast["size_verified"])
            self.assertFalse(fast["hash_verified"])
            self.assertTrue(full["hash_verified"])


if __name__ == "__main__":
    unittest.main()
