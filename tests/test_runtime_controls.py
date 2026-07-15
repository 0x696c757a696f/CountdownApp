import unittest
from dataclasses import replace
from unittest.mock import Mock, patch

from countdownapp.app import CountdownApp
from countdownapp.domain import AlgorithmMode, IntervalRange, SessionSettings, SessionState


class PausableSessionStub:
    def __init__(self):
        self.state = SessionState.FOCUSING
        self.reminder_visible = True
        self.is_long_break = False

    def pause(self):
        self.reminder_visible = False
        self.state = SessionState.PAUSED


class RuntimeControlTests(unittest.TestCase):
    def test_start_confirmation_explains_when_settings_can_produce_no_reminder(self):
        app = CountdownApp.__new__(CountdownApp)
        settings = replace(
            SessionSettings.defaults(
                focus_duration_sec=2 * 60,
                algorithm_mode=AlgorithmMode.CLASSIC,
            ),
            classic_interval=IntervalRange(3 * 60, 5 * 60),
        )

        with patch("countdownapp.app.messagebox.askyesno", return_value=False) as ask:
            confirmed = app._confirm_reminder_coverage(settings)

        self.assertFalse(confirmed)
        self.assertIn("不会产生随机提醒", ask.call_args.args[1])

    def test_pausing_focus_closes_a_visible_reminder_without_return_bell(self):
        app = CountdownApp.__new__(CountdownApp)
        app.session = PausableSessionStub()
        app.audio = Mock()
        app.pause_button = Mock()
        app._close_reminder = Mock()
        app._update_focus_display = Mock()

        app._toggle_pause()

        app._close_reminder.assert_called_once_with(dismiss=False)
        app.audio.pause_ambient.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
