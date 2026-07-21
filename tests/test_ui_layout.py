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

    def _button(self, text):
        return next(
            widget
            for widget in self._descendants(self.app.settings_view.frame)
            if isinstance(widget, ttk.Button) and widget.cget("text") == text
        )

    def test_product_title_is_chinese_and_uses_release_version(self):
        visible_labels = {
            widget.cget("text")
            for widget in self._descendants(self.app.settings_view.frame)
            if isinstance(widget, ttk.Label) and widget.winfo_ismapped()
        }

        self.assertEqual("随机专注计时器 3.0", self.root.title())
        self.assertIn("随机专注计时器 3.0", visible_labels)
        self.assertFalse(any("CountdownApp" in text for text in visible_labels))

    def test_algorithm_and_frequency_keep_their_standard_names(self):
        self._button("更多设置 ▾").invoke()
        self.root.update_idletasks()
        visible_copy = [self.root.title()]
        for widget in self._descendants(self.app.settings_view.frame):
            if not widget.winfo_ismapped():
                continue
            try:
                visible_copy.append(str(widget.cget("text")))
            except tk.TclError:
                pass
            if isinstance(widget, ttk.Combobox):
                visible_copy.extend(map(str, widget.cget("values")))

        combined = "\n".join(visible_copy)
        self.assertNotIn("CountdownApp", combined)
        self.assertIn("Classic", combined)
        self.assertIn("V2", combined)
        self.assertIn("Solfeggio 528 Hz", combined)

    def test_v2_and_more_settings_actions_share_one_horizontal_row(self):
        v2_y = self._button("调整 V2").winfo_rooty()
        more_y = self._button("更多设置 ▾").winfo_rooty()

        self.assertLessEqual(abs(v2_y - more_y), 2)

    def test_primary_settings_actions_are_fully_visible_without_scrolling(self):
        self.root.geometry("720x690+80+80")
        self.root.update()
        canvas = next(
            widget
            for widget in self._descendants(self.app.settings_view.frame)
            if isinstance(widget, tk.Canvas)
        )
        more_button = self._button("更多设置 ▾")
        viewport_bottom = (
            canvas.winfo_rooty()
            + canvas.winfo_height()
        )
        action_bottom = (
            more_button.winfo_rooty() + more_button.winfo_height()
        )

        self.assertLessEqual(action_bottom, viewport_bottom)

    def test_primary_numeric_fields_stay_compact_in_a_wide_window(self):
        self.root.geometry("1100x710+80+80")
        self.root.update()
        fields = [
            widget
            for widget in self._descendants(self.app.settings_view.frame)
            if isinstance(widget, ttk.Entry) and widget.winfo_ismapped()
        ]

        self.assertTrue(fields)
        self.assertLessEqual(max(field.winfo_width() for field in fields), 320)

    def test_more_settings_action_remains_visible_in_classic_mode(self):
        self.app.algorithm_var.set("Classic")
        self.app.settings_view.refresh_algorithm()
        self.root.update_idletasks()

        self.assertFalse(self._button("调整 V2").winfo_ismapped())
        self.assertTrue(self._button("更多设置 ▾").winfo_ismapped())

    def test_expanding_more_settings_keeps_the_collapse_action_visible(self):
        self.root.geometry("720x690+80+80")
        self.root.update()

        self._button("更多设置 ▾").invoke()
        self.root.update()
        canvas = next(
            widget
            for widget in self._descendants(self.app.settings_view.frame)
            if isinstance(widget, tk.Canvas)
        )
        collapse = self._button("收起更多设置 ▴")
        viewport_top = canvas.winfo_rooty()
        viewport_bottom = viewport_top + canvas.winfo_height()
        button_top = collapse.winfo_rooty()
        button_bottom = button_top + collapse.winfo_height()
        self.assertGreaterEqual(button_top, viewport_top)
        self.assertLessEqual(button_bottom, viewport_bottom)

    def test_adaptive_feedback_setting_explains_buttons_and_effect(self):
        self._button("更多设置 ▾").invoke()
        self.root.update_idletasks()
        labels = {
            widget.cget("text")
            for widget in self._descendants(self.app.settings_view.frame)
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
        self.app.settings_view.hide()
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
        self.app.settings_view.hide()
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
        self.app.settings_view.hide()
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

    def test_high_dpi_runtime_details_do_not_clip_the_action_row(self):
        old_scaling = float(self.root.tk.call("tk", "scaling"))
        try:
            self.root.tk.call("tk", "scaling", 168 / 72)
            self.app.settings_view.hide()
            self.app.runtime_view.show_focus("粉红噪音 + Solfeggio 852 Hz · 20%")
            self.app.runtime_view.render(
                RuntimeDisplay(
                    "89:57",
                    "注意力锚定期",
                    "当前基础随机区间：4–7 分钟 ｜ 自适应反馈开启",
                    "本轮反馈：仍在任务 0 · 走神 0 · 延后下次提醒 0",
                )
            )
            self.root.update()
            hide_button = next(
                widget
                for widget in self._descendants(self.app.runtime_view.frame)
                if isinstance(widget, ttk.Button)
                and widget.cget("text") == "隐藏到托盘"
            )
            button_bottom = hide_button.winfo_rooty() + hide_button.winfo_height()
            window_bottom = self.root.winfo_rooty() + self.root.winfo_height()

            self.assertLessEqual(button_bottom + 12, window_bottom)
        finally:
            self.root.tk.call("tk", "scaling", old_scaling)

    def test_break_prompt_expands_to_show_every_action(self):
        self.app.settings_view.hide()
        self.app.break_prompt_view.show()
        self.root.update_idletasks()

        self.assertGreaterEqual(
            self.root.winfo_height(), self.app.break_prompt_view.required_height
        )


if __name__ == "__main__":
    unittest.main()
