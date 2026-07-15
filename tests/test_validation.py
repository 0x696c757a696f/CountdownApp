import unittest
from dataclasses import replace

from countdownapp.domain import AlgorithmMode, SessionSettings, validate_settings


class SettingsValidationTests(unittest.TestCase):
    def test_classic_mode_ignores_stale_v2_boundaries(self):
        original = SessionSettings.defaults(
            focus_duration_sec=90 * 60,
            algorithm_mode=AlgorithmMode.V2,
        )
        classic = replace(
            original,
            focus_duration_sec=30 * 60,
            algorithm_mode=AlgorithmMode.CLASSIC,
        )

        errors = validate_settings(classic)

        self.assertEqual([], errors)


if __name__ == "__main__":
    unittest.main()
