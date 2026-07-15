import tkinter as tk
import unittest
from unittest.mock import Mock
from tkinter import ttk

from countdownapp.break_prompt_view import BreakPromptBindings, BreakPromptView


class BreakPromptViewTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f"Tk is unavailable: {error}")
        self.root.geometry("+10000+10000")
        self.bindings = BreakPromptBindings(
            duration_var=tk.StringVar(value="20"),
            on_start=Mock(),
            on_skip=Mock(),
            on_shutdown=Mock(),
        )
        self.view = BreakPromptView(self.root, self.bindings)

    def tearDown(self):
        if hasattr(self, "root"):
            self.root.destroy()

    @staticmethod
    def _buttons(widget):
        buttons = {}
        for child in widget.winfo_children():
            if isinstance(child, ttk.Button):
                buttons[child.cget("text")] = child
            buttons.update(BreakPromptViewTests._buttons(child))
        return buttons

    def test_show_owns_responsive_layout_and_all_actions(self):
        self.view.show()
        self.root.update_idletasks()

        self.assertTrue(self.view.is_visible)
        self.assertGreaterEqual(self.root.winfo_height(), self.view.required_height)
        buttons = self._buttons(self.view.frame)
        self.assertEqual({"开始休息", "跳过", "退出程序"}, set(buttons))

        buttons["开始休息"].invoke()
        buttons["跳过"].invoke()
        buttons["退出程序"].invoke()
        self.bindings.on_start.assert_called_once_with()
        self.bindings.on_skip.assert_called_once_with()
        self.bindings.on_shutdown.assert_called_once_with()

    def test_hide_removes_the_page(self):
        self.view.show()
        self.view.hide()

        self.assertFalse(self.view.is_visible)


if __name__ == "__main__":
    unittest.main()
