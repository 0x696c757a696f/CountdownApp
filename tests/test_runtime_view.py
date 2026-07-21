import tkinter as tk
import unittest
from tkinter import ttk
from unittest.mock import Mock

from countdownapp.runtime_view import RuntimeBindings, RuntimeDisplay, RuntimeView


class RuntimeViewTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f"Tk is unavailable: {error}")
        self.root.geometry("+10000+10000")
        self.bindings = RuntimeBindings(
            noise_var=tk.StringVar(value="粉红噪音"),
            texture_var=tk.StringVar(value="风雨雷暴"),
            tone_var=tk.StringVar(value="关闭"),
            volume_var=tk.DoubleVar(value=20),
            volume_label_var=tk.StringVar(value="20%"),
            on_ambient_change=Mock(),
            on_volume_change=Mock(),
            on_volume_commit=Mock(),
            on_stop_ambient=Mock(),
            on_pause=Mock(),
            on_stop_focus=Mock(),
            on_hide=Mock(),
        )
        self.view = RuntimeView(
            self.root,
            self.bindings,
            noise_options=("关闭", "粉红噪音"),
            texture_options=("关闭", "风雨雷暴", "雨声"),
            tone_options=("关闭", "Solfeggio 528 Hz"),
        )

    def tearDown(self):
        if hasattr(self, "root"):
            self.root.destroy()

    @staticmethod
    def _texts(widget):
        values = []
        for child in widget.winfo_children():
            try:
                values.append(child.cget("text"))
            except tk.TclError:
                pass
            values.extend(RuntimeViewTests._texts(child))
        return values

    @staticmethod
    def _descendants(widget):
        for child in widget.winfo_children():
            yield child
            yield from RuntimeViewTests._descendants(child)

    def test_entering_focus_shows_a_compact_collapsed_runtime_page(self):
        self.view.show_focus("粉红噪音 · 20%")
        self.root.update()

        self.assertTrue(self.view.is_visible)
        self.assertFalse(self.view.ambient_controls_expanded)
        self.assertIn("暂停专注", self._texts(self.root))
        self.assertIn("粉红噪音 · 20%", self._texts(self.root))

    def test_expanded_controls_offer_three_combinable_layers(self):
        self.view.show_focus("粉红噪音 + 风雨雷暴 · 20%")
        self.view.toggle_ambient_controls()
        self.root.update_idletasks()

        texts = self._texts(self.root)
        self.assertIn("基础噪音", texts)
        self.assertIn("环境录音", texts)
        self.assertIn("Solfeggio", texts)

    def test_session_detail_changes_remeasure_layout_but_timer_ticks_do_not(self):
        self.view.show_focus("已关闭")
        self.view.apply_window_layout = Mock()

        self.view.render(
            RuntimeDisplay("25:00", "注意力锚定期", "当前基础随机区间：4–7 分钟")
        )

        self.view.apply_window_layout.assert_called_once_with()
        self.view.apply_window_layout.reset_mock()

        self.view.render(
            RuntimeDisplay("24:59", "注意力锚定期", "当前基础随机区间：4–7 分钟")
        )

        self.view.apply_window_layout.assert_not_called()

    def test_rendering_wrapped_session_details_keeps_actions_visible(self):
        old_scaling = float(self.root.tk.call("tk", "scaling"))
        try:
            self.root.tk.call("tk", "scaling", 168 / 72)
            self.view.show_focus("粉红噪音 + Solfeggio 852 Hz · 20%")
            self.view.render(
                RuntimeDisplay(
                    "89:57",
                    "注意力锚定期",
                    "当前基础随机区间：4–7 分钟 ｜ 自适应反馈开启",
                    "本轮反馈：仍在任务 0 · 走神 0 · 延后下次提醒 0",
                )
            )
            self.root.update()
            action_bottom = max(
                child.winfo_rooty() + child.winfo_height()
                for child in self._descendants(self.root)
                if isinstance(child, ttk.Button)
                and child.cget("text") in {"暂停专注", "结束专注", "隐藏到托盘"}
            )
            window_bottom = self.root.winfo_rooty() + self.root.winfo_height()

            self.assertLessEqual(action_bottom + 12, window_bottom)
        finally:
            self.root.tk.call("tk", "scaling", old_scaling)


if __name__ == "__main__":
    unittest.main()
