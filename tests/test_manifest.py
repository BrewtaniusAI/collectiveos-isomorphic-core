from __future__ import annotations

import unittest

from oims.manifest import load_manifest


class ManifestTests(unittest.TestCase):
    def test_all_weight_tiers_are_pinned(self) -> None:
        manifest = load_manifest()
        self.assertEqual(["ISO-1B", "ISO-7B", "ISO-30B"], [tier.name for tier in manifest.tiers])
        for tier in manifest.tiers:
            self.assertEqual(40, len(tier.revision))
            self.assertTrue(tier.weight_files)
            for weight_file in tier.weight_files:
                self.assertEqual(64, len(weight_file.sha256))
                self.assertGreater(weight_file.size, 0)

    def test_family_requires_distinct_architectures_and_providers(self) -> None:
        manifest = load_manifest()
        self.assertEqual("heterogeneous-architecture-required", manifest.diversity_policy)
        self.assertEqual(
            {"qwen2", "mistral", "kimi-linear"},
            {tier.architecture_family for tier in manifest.tiers},
        )
        self.assertEqual(3, len({tier.provider for tier in manifest.tiers}))
        self.assertEqual(
            tuple(tier.name for tier in manifest.tiers),
            manifest.mesh.members,
        )

    def test_chat_system_modes_are_explicit(self) -> None:
        manifest = load_manifest()
        self.assertEqual("native", manifest.tier("ISO-1B").chat_system_mode)
        self.assertEqual("prepend-user", manifest.tier("ISO-7B").chat_system_mode)
        self.assertEqual("native", manifest.tier("ISO-30B").chat_system_mode)


if __name__ == "__main__":
    unittest.main()
