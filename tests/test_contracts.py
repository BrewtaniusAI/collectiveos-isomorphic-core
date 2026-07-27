from __future__ import annotations

import unittest

from oims.contracts import load_contract, validate_input, validate_output


class ContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.contract = load_contract()

    def test_normal_input_executes(self) -> None:
        decision = validate_input("family conformance probe", self.contract)
        self.assertTrue(decision.lawful)
        self.assertTrue(decision.should_execute)
        self.assertEqual("LAWFUL", decision.status)

    def test_empty_input_is_idle_without_execution(self) -> None:
        decision = validate_input("   ", self.contract)
        self.assertTrue(decision.lawful)
        self.assertFalse(decision.should_execute)
        self.assertEqual("IDLE", decision.status)

    def test_non_string_collapses_before_execution(self) -> None:
        decision = validate_input(42, self.contract)
        self.assertFalse(decision.lawful)
        self.assertFalse(decision.should_execute)
        self.assertEqual("DIGITAL_APOPTOSIS", decision.status)

    def test_length_boundary(self) -> None:
        accepted = validate_input("x" * self.contract.input_max_length, self.contract)
        rejected = validate_input("x" * (self.contract.input_max_length + 1), self.contract)
        self.assertTrue(accepted.should_execute)
        self.assertEqual("DIGITAL_APOPTOSIS", rejected.status)

    def test_empty_model_output_collapses(self) -> None:
        decision = validate_output("", self.contract)
        self.assertEqual("DIGITAL_APOPTOSIS", decision.status)


if __name__ == "__main__":
    unittest.main()
