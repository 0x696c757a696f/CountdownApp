import unittest

from countdownapp.display import DesktopBounds, cover_virtual_desktop, virtual_desktop_bounds


class FakeWindow:
    def __init__(self):
        self.geometry_value = ""
        self.updated = False

    def geometry(self, value):
        self.geometry_value = value

    def update_idletasks(self):
        self.updated = True

    def winfo_id(self):
        return 42

    def winfo_screenwidth(self):
        return 1920

    def winfo_screenheight(self):
        return 1080


class DisplayTests(unittest.TestCase):
    def test_reads_the_complete_virtual_desktop_with_a_negative_origin(self):
        values = {76: -1920, 77: -180, 78: 4480, 79: 1620}

        self.assertEqual(
            DesktopBounds(-1920, -180, 4480, 1620),
            virtual_desktop_bounds(values.__getitem__),
        )

    def test_native_positioning_receives_absolute_virtual_desktop_coordinates(self):
        window = FakeWindow()
        calls = []
        bounds = DesktopBounds(-1920, 0, 3840, 1080)

        cover_virtual_desktop(
            window,
            bounds=bounds,
            native_setter=lambda handle, area: calls.append((handle, area)),
        )

        self.assertEqual("3840x1080+0+0", window.geometry_value)
        self.assertTrue(window.updated)
        self.assertEqual([(42, bounds)], calls)

    def test_native_positioning_failure_keeps_a_primary_screen_fallback(self):
        window = FakeWindow()
        bounds = DesktopBounds(-1920, 0, 3840, 1080)

        cover_virtual_desktop(
            window,
            bounds=bounds,
            native_setter=lambda _handle, _area: (_ for _ in ()).throw(OSError()),
        )

        self.assertEqual("1920x1080+0+0", window.geometry_value)


if __name__ == "__main__":
    unittest.main()
