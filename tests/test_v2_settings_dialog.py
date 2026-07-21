import tkinter as tk
import unittest
from unittest.mock import Mock

from countdownapp.config import AppSettings
from countdownapp.settings_form import SettingsForm
from countdownapp.v2_settings_dialog import V2SettingsDialog


class V2SettingsDialogTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f"Tk is unavailable: {error}")
        self.root.geometry("+10000+10000")
        self.form = SettingsForm(self.root)
        self.form.load(AppSettings())
        self.on_reset = Mock()
        self.on_closed = Mock()
        self.apply_icon = Mock()
        self.dialog = V2SettingsDialog(
            self.root,
            self.form,
            on_reset=self.on_reset,
            on_closed=self.on_closed,
            apply_icon=self.apply_icon,
        )

    def tearDown(self):
        if hasattr(self, "dialog"):
            self.dialog.close()
        if hasattr(self, "root"):
            self.root.destroy()

    def test_repeated_show_reuses_one_dialog_window(self):
        self.dialog.show()
        first_windows = [
            child for child in self.root.winfo_children() if isinstance(child, tk.Toplevel)
        ]

        self.dialog.show()
        second_windows = [
            child for child in self.root.winfo_children() if isinstance(child, tk.Toplevel)
        ]

        self.assertTrue(self.dialog.is_open)
        self.assertEqual(1, len(first_windows))
        self.assertEqual(first_windows, second_windows)

    def test_dialog_receives_the_application_icon(self):
        self.dialog.show()
        window = next(
            child
            for child in self.root.winfo_children()
            if isinstance(child, tk.Toplevel)
        )

        self.apply_icon.assert_called_once_with(window)

    def test_close_notifies_the_owner_once(self):
        self.dialog.show()

        self.dialog.close()
        self.dialog.close()

        self.assertFalse(self.dialog.is_open)
        self.on_closed.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
