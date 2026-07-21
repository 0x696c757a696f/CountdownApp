import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from countdownapp.app import CountdownApp
from countdownapp.app_icon import (
    apply_child_window_icon,
    apply_window_icon,
    apply_windows_native_icons,
    configure_dpi_awareness,
    configure_process_identity,
)


class RootStub:
    def __init__(self):
        self.events = []

    def iconphoto(self, default, image):
        self.events.append(("iconphoto", default, image))

    def iconbitmap(self, *, bitmap):
        self.events.append(("iconbitmap", bitmap))


class AppIconTests(unittest.TestCase):
    def test_application_applies_its_loaded_icon_to_child_windows(self):
        app = CountdownApp.__new__(CountdownApp)
        app.app_icon = object()
        app.logger = Mock()
        window = Mock()

        with patch("countdownapp.app.apply_child_window_icon") as apply_icon:
            app._apply_child_window_icon(window)

        apply_icon.assert_called_once_with(window, app.app_icon)

    def test_child_window_reuses_the_same_icon_family(self):
        window = RootStub()
        photo = object()

        apply_child_window_icon(
            window,
            photo,
            resolve_resource=lambda name: Path("bundle") / name,
            platform_name="linux",
        )

        self.assertEqual(
            [
                ("iconphoto", False, photo),
                ("iconbitmap", str(Path("bundle") / "clock_icon.ico")),
            ],
            window.events,
        )

    def test_windows_enables_per_monitor_v2_before_creating_windows(self):
        contexts = []

        configured = configure_dpi_awareness(
            platform_name="win32",
            setter=contexts.append,
        )

        self.assertTrue(configured)
        self.assertEqual([-4], contexts)

    def test_windows_loads_distinct_icons_for_the_current_dpi(self):
        class WindowStub:
            def update_idletasks(self):
                pass

            def winfo_id(self):
                return 100

        class NativeApiStub:
            def __init__(self):
                self.loaded_sizes = []
                self.applied = []

            def top_level_handle(self, child_handle):
                self.assert_value(child_handle, 100)
                return 200

            def dpi_for_window(self, window_handle):
                self.assert_value(window_handle, 200)
                return 168

            def metric_for_dpi(self, metric, dpi):
                self.assert_value(dpi, 168)
                return {49: 28, 11: 56}[metric]

            def load_icon(self, path, size):
                self.loaded_sizes.append((path, size))
                return size * 10

            def set_icon(self, window_handle, kind, icon_handle):
                self.applied.append((window_handle, kind, icon_handle))

            @staticmethod
            def assert_value(actual, expected):
                if actual != expected:
                    raise AssertionError((actual, expected))

        native = NativeApiStub()

        handles = apply_windows_native_icons(
            WindowStub(),
            Path("bundle") / "clock_icon.ico",
            native_api=native,
        )

        self.assertEqual(
            [(Path("bundle") / "clock_icon.ico", 28),
             (Path("bundle") / "clock_icon.ico", 56)],
            native.loaded_sizes,
        )
        self.assertEqual([(200, 0, 280), (200, 1, 560)], native.applied)
        self.assertEqual((280, 560), handles)

    def test_windows_process_uses_a_stable_taskbar_identity(self):
        app_ids = []

        configured = configure_process_identity(
            platform_name="win32",
            setter=app_ids.append,
        )

        self.assertTrue(configured)
        self.assertEqual(["CountdownApp.FocusTimer"], app_ids)

    def test_one_icon_family_is_applied_to_the_root_and_child_windows(self):
        root = RootStub()
        photo = object()

        retained = apply_window_icon(
            root,
            resolve_resource=lambda name: Path("bundle") / name,
            image_factory=lambda path: photo,
            platform_name="linux",
        )

        self.assertIs(photo, retained)
        self.assertEqual(
            [
                ("iconphoto", True, photo),
                ("iconbitmap", str(Path("bundle") / "clock_icon.ico")),
            ],
            root.events,
        )


if __name__ == "__main__":
    unittest.main()
