from __future__ import annotations

import json
import unittest

from oims.manifest import ROOT


class SchemaTests(unittest.TestCase):
    def test_all_json_schemas_are_well_formed_json(self) -> None:
        schema_dir = ROOT / "schemas"
        expected = {
            "agent-manifest.schema.json",
            "collective-request.schema.json",
            "collective-response.schema.json",
            "family-conformance.schema.json",
            "model-forge-checkpoint.schema.json",
            "model-forge-plan.schema.json",
            "model-forge-preflight-receipt.schema.json",
            "model-forge-run-receipt.schema.json",
            "model-manifest.schema.json",
            "tier-conformance.schema.json",
        }
        self.assertEqual(expected, {path.name for path in schema_dir.glob("*.json")})
        for path in schema_dir.glob("*.json"):
            value = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(
                "https://json-schema.org/draft/2020-12/schema",
                value["$schema"],
            )
            self.assertIn("$id", value)

    def test_scope_ledger_and_sbom_are_machine_readable(self) -> None:
        scope = json.loads((ROOT / "SCOPE_MATRIX.json").read_text(encoding="utf-8"))
        self.assertEqual(
            "IN_REPO_COMPLETE_TARGET_ACCEPTANCE_PENDING",
            scope["scope_status"],
        )
        ids = {item["id"] for item in scope["components"]}
        self.assertIn("heterogeneous-family", ids)
        self.assertIn("collective-agent-bindings", ids)
        self.assertIn("dependency-supply-chain", ids)
        sbom = json.loads((ROOT / "SBOM.spdx.json").read_text(encoding="utf-8"))
        self.assertEqual("SPDX-2.3", sbom["spdxVersion"])
        self.assertEqual(4, len(sbom["packages"]))


if __name__ == "__main__":
    unittest.main()
