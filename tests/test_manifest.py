from __future__ import annotations

import unittest

from oims.manifest import load_manifest


class ManifestTests(unittest.TestCase):
    def test_all_weight_tiers_are_pinned(self) -> None:
        manifest = load_manifest()
        self.assertEqual(["ISO-1B", "ISO-7B", "ISO-30B"], [tier.name for tier in manifest.tiers])
        for tier in manifest.tiers:
            self.assertEqual(40, len(tier.revision))
            self.assertTrue(tier.files)
            self.assertEqual("Apache-2.0", tier.license)
            self.assertEqual("Q4_K_M", tier.quantization)

    def test_family_uses_one_base_model_line(self) -> None:
        manifest = load_manifest()
        self.assertTrue(all(tier.repo_id.startswith("Qwen/Qwen2.5-") for tier in manifest.tiers))


if __name__ == "__main__":
    unittest.main()
