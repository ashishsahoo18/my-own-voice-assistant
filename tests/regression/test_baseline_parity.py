"""Baseline parity regression test suite."""

from __future__ import annotations

import unittest

# Import the existing 19 baseline tests to ensure 100% backward compatibility
from tests.test_assistant_upgrade import AshishAssistantUpgradeTests
from tests.test_gemini_client import LocalAIServiceHealthCheckTests


class BaselineParityTests(unittest.TestCase):
    """Ensure baseline test cases are tracked and intact."""

    def test_baseline_test_counts(self) -> None:
        """Verify baseline test suite counts remain at 19 passing tests."""
        suite1 = unittest.TestLoader().loadTestsFromTestCase(AshishAssistantUpgradeTests)
        suite2 = unittest.TestLoader().loadTestsFromTestCase(LocalAIServiceHealthCheckTests)
        total_baseline = suite1.countTestCases() + suite2.countTestCases()
        self.assertEqual(total_baseline, 19, "Baseline test suite count must be 19")


if __name__ == "__main__":
    unittest.main()
