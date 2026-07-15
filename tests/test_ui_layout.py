import tkinter as tk
import unittest
from types import SimpleNamespace
from tkinter import ttk

from countdownapp.app import CountdownApp


class SettingsActionLayoutTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f"Tk is unavailable: {error}")
        self.app = CountdownApp.__new__(CountdownApp)
        self.app.root = self.root
        self.app.audio = SimpleNamespace(stop_ambient=lambda: None)
        self.app._configure_root()
        self.root.geometry("+10000+10000")
        self.app._build_ui()
        self.root.update()

    def tearDown(self):
        if hasattr(self, "root"):
            self.root.destroy()

    @staticmethod
    def _descendants(widget):
        for child in widget.winfo_children():
            yield child
            yield from SettingsActionLayoutTests._descendants(child)

    def test_v2_and_more_settings_actions_share_one_horizontal_row(self):
        v2_y = self.app.v2_settings_button.winfo_rooty()
        more_y = self.app.more_button.winfo_rooty()

        self.assertLessEqual(abs(v2_y - more_y), 2)

    def test_primary_settings_actions_are_fully_visible_without_scrolling(self):
        self.root.geometry("720x690+80+80")
        self.root.update()
        viewport_bottom = (
            self.app.basic_canvas.winfo_rooty()
            + self.app.basic_canvas.winfo_height()
        )
        action_bottom = (
            self.app.more_button.winfo_rooty() + self.app.more_button.winfo_height()
        )

        self.assertLessEqual(action_bottom, viewport_bottom)

    def test_more_settings_action_remains_visible_in_classic_mode(self):
        self.app.algorithm_var.set("Classic")
        self.app._refresh_algorithm_controls()
        self.root.update_idletasks()

        self.assertFalse(self.app.v2_settings_button.winfo_ismapped())
        self.assertTrue(self.app.more_button.winfo_ismapped())

    def test_expanding_more_settings_keeps_the_collapse_action_visible(self):
        self.root.geometry("720x690+80+80")
        self.root.update()

        self.app._toggle_more_settings()
        self.root.update()

        viewport_top = self.app.basic_canvas.winfo_rooty()
        viewport_bottom = viewport_top + self.app.basic_canvas.winfo_height()
        button_top = self.app.more_button.winfo_rooty()
        button_bottom = button_top + self.app.more_button.winfo_height()
        self.assertGreaterEqual(button_top, viewport_top)
        self.assertLessEqual(button_bottom, viewport_bottom)

    def test_v2_editor_groups_boundaries_and_interval_columns_compactly(self):
        self.app._open_v2_settings()
        self.root.update_idletasks()
        window = self.app.v2_window
        descendants = tuple(self._descendants(window))

        sections = {
            widget.cget("text")
            for widget in descendants
            if isinstance(widget, ttk.LabelFrame)
        }
        labels = {
            widget.cget("text")
            for widget in descendants
            if isinstance(widget, ttk.Label)
        }

        self.assertEqual({"阶段边界", "阶段随机间隔（分钟）"}, sections)
        self.assertTrue({"阶段", "最小", "最大"}.issubset(labels))
        self.assertEqual((560, 430), (window.winfo_width(), window.winfo_height()))
        body = window.winfo_children()[0]
        self.assertGreaterEqual(window.winfo_height(), body.winfo_reqheight())

    def test_runtime_ambient_controls_are_compact_until_requested(self):
        self.assertEqual("pack", self.app.runtime_ambient_bar.winfo_manager())
        self.assertEqual("", self.app.runtime_ambient_controls.winfo_manager())

        self.app._toggle_runtime_ambient_controls()
        self.root.update_idletasks()

        self.assertEqual("pack", self.app.runtime_ambient_controls.winfo_manager())
        self.assertEqual("收起", self.app.runtime_ambient_toggle_button.cget("text"))
        self.assertEqual((600, 460), (self.root.winfo_width(), self.root.winfo_height()))

    def test_timer_and_session_details_share_the_dashboard_row(self):
        self.app.settings_frame.pack_forget()
        self.app.running_frame.pack(fill="both", expand=True)
        self.root.update_idletasks()

        timer_y = self.app.timer_label.winfo_rooty()
        phase_y = self.app.phase_label.winfo_rooty()

        self.assertLess(abs(timer_y - phase_y), 80)

    def test_runtime_actions_use_two_aligned_button_rows(self):
        self.app.settings_frame.pack_forget()
        self.app.running_frame.pack(fill="both", expand=True)
        self.app._toggle_runtime_ambient_controls()
        self.root.update_idletasks()

        self.assertLessEqual(
            abs(
                self.app.runtime_ambient_stop_button.winfo_rooty()
                - self.app.runtime_ambient_toggle_button.winfo_rooty()
            ),
            2,
        )
        bottom_buttons = (
            self.app.pause_button,
            self.app.stop_focus_button,
            self.app.hide_to_tray_button,
        )
        self.assertEqual(1, len({button.winfo_rooty() for button in bottom_buttons}))
        self.assertLessEqual(
            max(button.winfo_width() for button in bottom_buttons)
            - min(button.winfo_width() for button in bottom_buttons),
            1,
        )
        self.assertGreaterEqual(
            self.app.runtime_ambient_summary_label.winfo_width(),
            min(self.app.runtime_ambient_summary_label.winfo_reqwidth(), 260),
        )
        self.assertGreaterEqual(
            self.root.winfo_height(), self.app.running_frame.winfo_reqheight()
        )
        button_bottom = (
            self.app.hide_to_tray_button.winfo_rooty()
            - self.root.winfo_rooty()
            + self.app.hide_to_tray_button.winfo_height()
        )
        self.assertGreaterEqual(self.root.winfo_height() - button_bottom, 12)
        self.assertEqual(460, self.root.minsize()[1])

    def test_break_prompt_expands_to_show_every_action(self):
        self.app.settings_frame.pack_forget()
        self.app.break_prompt_frame.pack(fill="both", expand=True)

        self.app._apply_break_prompt_window_layout()
        self.root.update_idletasks()

        self.assertGreaterEqual(
            self.root.winfo_height(), self.app.break_prompt_frame.winfo_reqheight()
        )


if __name__ == "__main__":
    unittest.main()
