import tkinter as tk
import unittest
from unittest.mock import Mock

from countdownapp.runtime_view import RuntimeBindings, RuntimeView


class RuntimeViewTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f"Tk is unavailable: {error}")
        self.root.geometry("+10000+10000")
        self.bindings = RuntimeBindings(
            noise_var=tk.StringVar(value="粉红噪音"),
            texture_var=tk.StringVar(value="柔和雨声"),
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
            texture_options=("关闭", "柔和雨声"),
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

    def test_entering_focus_shows_a_compact_collapsed_runtime_page(self):
        self.view.show_focus("粉红噪音 · 20%")
        self.root.update_idletasks()

        self.assertTrue(self.view.is_visible)
        self.assertFalse(self.view.ambient_controls_expanded)
        self.assertIn("暂停专注", self._texts(self.root))
        self.assertIn("粉红噪音 · 20%", self._texts(self.root))

    def test_expanded_controls_offer_three_combinable_layers(self):
        self.view.show_focus("粉红噪音 + 柔和雨声 · 20%")
        self.view.toggle_ambient_controls()
        self.root.update_idletasks()

        texts = self._texts(self.root)
        self.assertIn("基础噪音", texts)
        self.assertIn("环境纹理", texts)
        self.assertIn("Solfeggio", texts)


if __name__ == "__main__":
    unittest.main()
