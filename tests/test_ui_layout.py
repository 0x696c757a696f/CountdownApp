import tkinter as tk
import unittest
from types import SimpleNamespace
from tkinter import ttk

from countdownapp.app import CountdownApp
from countdownapp.runtime_view import RuntimeDisplay


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

    def test_adaptive_feedback_setting_explains_buttons_and_effect(self):
        labels = {
            widget.cget("text")
            for widget in self._descendants(self.app.more_frame)
            if isinstance(widget, (ttk.Label, ttk.Checkbutton))
        }

        self.assertIn(
            "在提醒中显示反馈按钮：仍在任务 / 刚才走神 / 正在心流，延后下次提醒",
            labels,
        )
        self.assertIn("根据反馈自动调整下一次提醒间隔", labels)

    def test_v2_editor_groups_boundaries_and_interval_columns_compactly(self):
        self.app._open_v2_settings()
        self.root.update_idletasks()
        window = next(
            child
            for child in self.root.winfo_children()
            if isinstance(child, tk.Toplevel)
        )
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
        self.app.settings_frame.pack_forget()
        self.app.runtime_view.show_focus("已关闭")
        self.assertFalse(self.app.runtime_view.ambient_controls_expanded)

        self.app._toggle_runtime_ambient_controls()
        self.root.update_idletasks()

        self.assertTrue(self.app.runtime_view.ambient_controls_expanded)
        texts = {
            widget.cget("text")
            for widget in self._descendants(self.app.runtime_view.frame)
            if isinstance(widget, (ttk.Label, ttk.Button))
        }
        self.assertIn("收起", texts)
        self.assertEqual((600, 460), (self.root.winfo_width(), self.root.winfo_height()))

    def test_timer_and_session_details_share_the_dashboard_row(self):
        self.app.settings_frame.pack_forget()
        self.app.runtime_view.show_focus("已关闭")
        self.app.runtime_view.render(
            RuntimeDisplay("56:42", "深度专注期", "当前基础随机区间：10–15 分钟")
        )
        self.root.update_idletasks()
        labels = {
            widget.cget("text"): widget
            for widget in self._descendants(self.app.runtime_view.frame)
            if isinstance(widget, ttk.Label)
        }
        timer_y = labels["56:42"].winfo_rooty()
        phase_y = labels["深度专注期"].winfo_rooty()

        self.assertLess(abs(timer_y - phase_y), 80)

    def test_runtime_actions_use_two_aligned_button_rows(self):
        self.app.settings_frame.pack_forget()
        self.app.runtime_view.show_focus("粉红噪音 · 20%")
        self.app._toggle_runtime_ambient_controls()
        self.root.update_idletasks()
        buttons = {
            widget.cget("text"): widget
            for widget in self._descendants(self.app.runtime_view.frame)
            if isinstance(widget, ttk.Button)
        }

        self.assertLessEqual(
            abs(
                buttons["关闭"].winfo_rooty()
                - buttons["收起"].winfo_rooty()
            ),
            2,
        )
        bottom_buttons = (
            buttons["暂停专注"],
            buttons["结束专注"],
            buttons["隐藏到托盘"],
        )
        self.assertEqual(1, len({button.winfo_rooty() for button in bottom_buttons}))
        self.assertLessEqual(
            max(button.winfo_width() for button in bottom_buttons)
            - min(button.winfo_width() for button in bottom_buttons),
            1,
        )
        self.assertGreaterEqual(
            self.root.winfo_height(), self.app.runtime_view.required_height
        )
        button_bottom = (
            buttons["隐藏到托盘"].winfo_rooty()
            - self.root.winfo_rooty()
            + buttons["隐藏到托盘"].winfo_height()
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
