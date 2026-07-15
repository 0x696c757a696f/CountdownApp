import tkinter as tk
import unittest
from tkinter import ttk

from countdownapp.adaptive import AttentionFeedback
from countdownapp.reminder_view import ReminderResult, ReminderResultKind, ReminderView


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

    def test_zero_duration_overlay_reports_automatic_completion(self):
        results = []

        from countdownapp.domain import ReminderPreset

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
