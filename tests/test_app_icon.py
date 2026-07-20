import unittest
from pathlib import Path

from countdownapp.app_icon import apply_window_icon, configure_process_identity


class RootStub:
    def __init__(self):
        self.events = []

    def iconphoto(self, default, image):
        self.events.append(("iconphoto", default, image))

    def iconbitmap(self, *, bitmap):
        self.events.append(("iconbitmap", bitmap))


class AppIconTests(unittest.TestCase):
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
