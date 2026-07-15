import unittest
from dataclasses import replace

from countdownapp.domain import (
    AlgorithmMode,
    IntervalRange,
    SessionSettings,
    reminder_coverage_warnings,
    validate_settings,
)


class SettingsValidationTests(unittest.TestCase):
    def test_warns_when_classic_interval_can_outlast_the_whole_session(self):
        settings = replace(
            SessionSettings.defaults(
                focus_duration_sec=2 * 60,
                algorithm_mode=AlgorithmMode.CLASSIC,
            ),
            classic_interval=IntervalRange(3 * 60, 5 * 60),
        )

        warnings = reminder_coverage_warnings(settings)

        self.assertEqual(1, len(warnings))
        self.assertIn("不会产生随机提醒", warnings[0])

    def test_warns_for_v2_phases_that_are_shorter_than_their_ranges(self):
        settings = SessionSettings.defaults(
            focus_duration_sec=15 * 60,
            algorithm_mode=AlgorithmMode.V2,
        )

        warnings = reminder_coverage_warnings(settings)

        self.assertTrue(any("注意力锚定期" in warning for warning in warnings))
        self.assertTrue(any("深度专注期" in warning for warning in warnings))
        self.assertTrue(any("疲劳维护期" in warning for warning in warnings))

    def test_default_ninety_minute_v2_has_full_reminder_coverage(self):
        settings = SessionSettings.defaults(
            focus_duration_sec=90 * 60,
            algorithm_mode=AlgorithmMode.V2,
        )

        self.assertEqual([], reminder_coverage_warnings(settings))

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
