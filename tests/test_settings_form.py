import tkinter as tk
import unittest
from dataclasses import replace

from countdownapp.config import AppSettings
from countdownapp.domain import (
    AlgorithmMode,
    IntervalRange,
    ReminderPreset,
    SessionSettings,
    V2Settings,
)
from countdownapp.settings_form import SettingsForm


class SettingsFormTests(unittest.TestCase):
    def setUp(self):
        self.tcl = tk.Tcl()
        self.form = SettingsForm(self.tcl)

    def test_session_settings_round_trip_through_the_form(self):
        session = SessionSettings(
            focus_duration_sec=75 * 60,
            algorithm_mode=AlgorithmMode.V2,
            classic_interval=IntervalRange(4 * 60, 6 * 60),
            v2=V2Settings(
                anchor_end_sec=25 * 60,
                fatigue_start_sec=55 * 60,
                anchor_interval=IntervalRange(3 * 60, 5 * 60),
                deep_focus_interval=IntervalRange(9 * 60, 13 * 60),
                fatigue_interval=IntervalRange(4 * 60, 7 * 60),
            ),
            reminder_preset=ReminderPreset.STRONG,
            microbreak_duration_sec=12,
            break_countdown_enabled=False,
            long_break_duration_sec=18 * 60,
            adaptive_reminders_enabled=True,
        )

        self.form.load(replace(AppSettings(), session=session))

        self.assertEqual(session, self.form.build_session_settings())

    def test_invalid_numeric_input_reports_the_field_name(self):
        self.form.load(AppSettings())
        self.form.total.set("九十")

        with self.assertRaisesRegex(ValueError, "总专注时间必须是数字"):
            self.form.build_session_settings()

    def test_building_app_settings_preserves_window_position(self):
        previous = replace(
            AppSettings(),
            floating_x=-640,
            floating_y=80,
        )
        self.form.load(previous)
        session = self.form.build_session_settings()

        result = self.form.build_app_settings(previous, session)

        self.assertEqual((-640, 80), (result.floating_x, result.floating_y))
        self.assertTrue(result.migration_completed)


if __name__ == "__main__":
    unittest.main()
