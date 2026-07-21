import tkinter as tk
import tkinter.font as tkfont
import unittest
from tkinter import ttk

from countdownapp.adaptive import AttentionFeedback
from countdownapp.domain import ReminderPreset
from countdownapp.reminder_view import (
    ReminderResult,
    ReminderResultKind,
    ReminderView,
    banner_action_columns,
)


class BannerActionLayoutTests(unittest.TestCase):
    def test_buttons_wrap_to_fit_the_available_screen_width(self):
        widths = (110, 110, 280, 90)

        self.assertEqual(4, banner_action_columns(widths, available_width=650))
        self.assertEqual(2, banner_action_columns(widths, available_width=480))
        self.assertEqual(1, banner_action_columns(widths, available_width=260))


class ReminderViewTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f"Tk is unavailable: {error}")
        self.root.geometry("+10000+10000")
        self.view = ReminderView(self.root)

    def tearDown(self):
        if hasattr(self, "view"):
            self.view.close()
        if hasattr(self, "root"):
            self.root.destroy()

    @staticmethod
    def _descendants(widget):
        for child in widget.winfo_children():
            yield child
            yield from ReminderViewTests._descendants(child)

    def test_adaptive_banner_reports_selected_feedback_and_closes(self):
        results = []

        self.view.show_banner(
            "我还在原任务上吗？",
            duration_sec=8,
            adaptive=True,
            on_result=results.append,
        )
        self.root.update_idletasks()
        window = next(
            widget for widget in self.root.winfo_children() if isinstance(widget, tk.Toplevel)
        )
        feedback_button = next(
            widget
            for widget in self._descendants(window)
            if isinstance(widget, ttk.Button) and widget.cget("text") == "仍在任务"
        )
        feedback_button.invoke()

        self.assertEqual(
            [ReminderResult(ReminderResultKind.FEEDBACK, AttentionFeedback.ON_TASK)],
            results,
        )
        self.assertFalse(self.view.is_open)

    def test_closing_programmatically_does_not_report_a_user_action(self):
        results = []
        self.view.show_banner("短暂休息", 8, False, results.append)

        self.view.close()

        self.assertEqual([], results)
        self.assertFalse(self.view.is_open)

    def test_banner_and_overlay_receive_the_application_icon(self):
        icon_windows = []
        view = ReminderView(self.root, apply_icon=icon_windows.append)

        view.show_banner("短暂休息", 8, False, lambda _result: None)
        banner = next(
            widget
            for widget in self.root.winfo_children()
            if isinstance(widget, tk.Toplevel)
        )
        self.assertEqual([banner], icon_windows)

        view.show_overlay(
            duration_sec=8,
            preset=ReminderPreset.BALANCED,
            adaptive=False,
            on_result=lambda _result: None,
        )
        overlay = next(
            widget
            for widget in self.root.winfo_children()
            if isinstance(widget, tk.Toplevel)
        )
        self.assertEqual([banner, overlay], icon_windows)
        view.close()

    def test_high_dpi_adaptive_banner_shows_every_complete_button_label(self):
        old_scaling = float(self.root.tk.call("tk", "scaling"))
        try:
            self.root.tk.call("tk", "scaling", 168 / 72)
            self.view.show_banner("我还在原任务上吗？", 8, True, lambda _result: None)
            self.root.update()
            window = next(
                widget
                for widget in self.root.winfo_children()
                if isinstance(widget, tk.Toplevel)
            )
            buttons = [
                widget
                for widget in self._descendants(window)
                if isinstance(widget, ttk.Button)
            ]
            style = ttk.Style(self.root)

            self.assertEqual(4, len(buttons))
            for button in buttons:
                font_name = style.lookup(button.cget("style") or "TButton", "font")
                text_width = tkfont.Font(root=self.root, font=font_name).measure(
                    button.cget("text")
                )
                self.assertGreaterEqual(button.winfo_width(), text_width + 24)
                self.assertLessEqual(
                    button.winfo_rootx() + button.winfo_width(),
                    window.winfo_rootx() + window.winfo_width() - 12,
                )
        finally:
            self.root.tk.call("tk", "scaling", old_scaling)

    def test_zero_duration_overlay_reports_automatic_completion(self):
        results = []

        self.view.show_overlay(
            duration_sec=0,
            preset=ReminderPreset.BALANCED,
            adaptive=False,
            on_result=results.append,
        )

        self.assertEqual(
            [ReminderResult(ReminderResultKind.COMPLETED)],
            results,
        )
        self.assertFalse(self.view.is_open)


if __name__ == "__main__":
    unittest.main()
