import unittest
from pathlib import Path

from countdownapp.app_icon import apply_window_icon


class RootStub:
    def __init__(self):
        self.events = []

    def iconphoto(self, default, image):
        self.events.append(("iconphoto", default, image))

    def iconbitmap(self, *, default):
        self.events.append(("iconbitmap", default))


class AppIconTests(unittest.TestCase):
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
