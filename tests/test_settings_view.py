import tkinter as tk
import unittest
from tkinter import ttk
from unittest.mock import Mock

from countdownapp.config import AppSettings
from countdownapp.settings_form import SettingsForm
from countdownapp.settings_view import SettingsView, SettingsViewBindings
from countdownapp.startup import StartupMode


class SettingsViewTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f"Tk is unavailable: {error}")
        self.root.geometry("+10000+10000")
        self.form = SettingsForm(self.root)
        self.form.load(AppSettings())
        self.bindings = SettingsViewBindings(
            on_open_v2=Mock(),
            on_test_audio=Mock(),
            on_choose_audio=Mock(),
            on_preview_ambient=Mock(),
            on_stop_ambient=Mock(),
            on_ambient_volume_change=Mock(),
            on_floating_status_change=Mock(),
            on_global_hotkeys_change=Mock(),
            on_close_to_tray_change=Mock(),
            on_startup_change=Mock(),
            on_start_focus=Mock(),
            on_shutdown=Mock(),
        )
        self.view = SettingsView(self.root, self.form, self.bindings)

    def tearDown(self):
        if hasattr(self, "root"):
            self.root.update_idletasks()
            self.root.destroy()

    @staticmethod
    def _texts(widget):
        result = []
        for child in widget.winfo_children():
            if isinstance(
                child,
                (ttk.Label, ttk.Button, ttk.Checkbutton, ttk.LabelFrame),
            ):
                result.append(child.cget("text"))
            result.extend(SettingsViewTests._texts(child))
        return result

    def test_show_displays_primary_actions_with_more_settings_collapsed(self):
        self.view.show()
        self.view.set_startup_mode(StartupMode.OFF)
        self.root.update_idletasks()

        texts = self._texts(self.root)
        self.assertTrue(self.view.is_visible)
        self.assertFalse(self.view.more_expanded)
        self.assertIn("开始专注", texts)
        self.assertIn("更多设置 ▾", texts)
        reminder_section = next(
            child
            for child in self._all_widgets(self.root)
            if isinstance(child, ttk.LabelFrame)
            and child.cget("text") == "提醒与铃声"
        )
        self.assertFalse(reminder_section.winfo_ismapped())

    def test_primary_start_action_is_forwarded_to_the_owner(self):
        self.view.show()
        start = next(
            child
            for child in self._all_widgets(self.root)
            if isinstance(child, ttk.Button) and child.cget("text") == "开始专注"
        )

        start.invoke()

        self.bindings.on_start_focus.assert_called_once_with()

    @staticmethod
    def _all_widgets(widget):
        for child in widget.winfo_children():
            yield child
            yield from SettingsViewTests._all_widgets(child)


if __name__ == "__main__":
    unittest.main()
