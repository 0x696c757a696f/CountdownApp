import tkinter as tk
import unittest
from types import SimpleNamespace

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
        self.root.update_idletasks()

    def tearDown(self):
        if hasattr(self, "root"):
            self.root.destroy()

    def test_v2_and_more_settings_actions_share_one_horizontal_row(self):
        v2_y = self.app.v2_settings_button.winfo_rooty()
        more_y = self.app.more_button.winfo_rooty()

        self.assertLessEqual(abs(v2_y - more_y), 2)

    def test_more_settings_action_remains_visible_in_classic_mode(self):
        self.app.algorithm_var.set("Classic")
        self.app._refresh_algorithm_controls()
        self.root.update_idletasks()

        self.assertFalse(self.app.v2_settings_button.winfo_ismapped())
        self.assertTrue(self.app.more_button.winfo_ismapped())


if __name__ == "__main__":
    unittest.main()
