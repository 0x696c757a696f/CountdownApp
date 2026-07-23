import queue
import unittest
from dataclasses import replace
from unittest.mock import Mock, patch

from countdownapp.app import CountdownApp
from countdownapp.domain import (
    AlgorithmMode,
    IntervalRange,
    SessionSettings,
    SessionState,
    V2Phase,
)


class FocusCoordinatorStub:
    def __init__(self):
        self.state = SessionState.FOCUSING

    def toggle_pause(self):
        self.state = SessionState.PAUSED
        return Mock(
            paused=True,
            reminder_was_visible=True,
            long_break=False,
            display=Mock(),
        )


class RuntimeControlTests(unittest.TestCase):
    @staticmethod
    def reminder_app(settings):
        app = CountdownApp.__new__(CountdownApp)
        app.focus = Mock(settings=settings)
        app.logger = Mock()
        app._show_banner = Mock()
        app._show_overlay = Mock()
        app.tray = Mock()
        app.audio = Mock()
        return app

    def test_classic_countdown_uses_a_small_window_until_fullscreen_is_enabled(self):
        settings = replace(
            SessionSettings.defaults(algorithm_mode=AlgorithmMode.CLASSIC),
            break_countdown_enabled=True,
            classic_fullscreen_reminders_enabled=False,
        )
        app = self.reminder_app(settings)

        app._show_reminder(None)

        app._show_banner.assert_called_once_with(
            "微休息：放松视线和肩颈。", settings.microbreak_duration_sec
        )
        app._show_overlay.assert_not_called()

    def test_v2_fatigue_countdown_uses_a_small_window_until_fullscreen_is_enabled(self):
        settings = replace(
            SessionSettings.defaults(algorithm_mode=AlgorithmMode.V2),
            break_countdown_enabled=True,
            v2_fatigue_fullscreen_reminders_enabled=False,
        )
        app = self.reminder_app(settings)

        app._show_reminder(V2Phase.FATIGUE_SUPPORT)

        app._show_banner.assert_called_once_with(
            "微休息：放松视线和肩颈。", settings.microbreak_duration_sec
        )
        app._show_overlay.assert_not_called()

    def test_classic_fullscreen_does_not_enable_v2_fatigue_fullscreen(self):
        settings = replace(
            SessionSettings.defaults(),
            break_countdown_enabled=True,
            classic_fullscreen_reminders_enabled=True,
            v2_fatigue_fullscreen_reminders_enabled=False,
        )

        classic_app = self.reminder_app(settings)
        classic_app._show_reminder(None)
        classic_app._show_overlay.assert_called_once()

        fatigue_app = self.reminder_app(settings)
        fatigue_app._show_reminder(V2Phase.FATIGUE_SUPPORT)
        fatigue_app._show_banner.assert_called_once()
        fatigue_app._show_overlay.assert_not_called()

    def test_v2_fatigue_fullscreen_does_not_enable_classic_fullscreen(self):
        settings = replace(
            SessionSettings.defaults(),
            break_countdown_enabled=True,
            classic_fullscreen_reminders_enabled=False,
            v2_fatigue_fullscreen_reminders_enabled=True,
        )

        classic_app = self.reminder_app(settings)
        classic_app._show_reminder(None)
        classic_app._show_banner.assert_called_once()
        classic_app._show_overlay.assert_not_called()

        fatigue_app = self.reminder_app(settings)
        fatigue_app._show_reminder(V2Phase.FATIGUE_SUPPORT)
        fatigue_app._show_overlay.assert_called_once_with(
            settings.microbreak_duration_sec,
            settings.reminder_preset,
        )

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
        app.focus = FocusCoordinatorStub()
        app.audio = Mock()
        app.runtime_view = Mock()
        app._close_reminder = Mock()
        app._render_focus_display = Mock()

        app._toggle_pause()

        app._close_reminder.assert_called_once_with(dismiss=False)
        app.audio.pause_ambient.assert_called_once_with()
        app.runtime_view.set_pause_state.assert_called_once_with(
            paused=True, long_break=False
        )

    def test_tray_can_restore_the_floating_timer(self):
        app = CountdownApp.__new__(CountdownApp)
        app.tray_after_id = None
        app.hotkeys = Mock()
        app.gui_callbacks = queue.Queue()
        app.tray_commands = queue.Queue()
        app.tray_commands.put("show_floating")
        app.root = Mock()
        app.root.after.return_value = "after-id"
        app.floating_status = Mock()

        app._poll_tray()

        app.floating_status.show_for_session.assert_called_once_with()
        self.assertEqual("after-id", app.tray_after_id)


if __name__ == "__main__":
    unittest.main()
