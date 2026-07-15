import unittest

from countdownapp.presentation import RenderCache


class RenderCacheTests(unittest.TestCase):
    def test_only_renders_when_a_display_value_changes(self):
        rendered = []
        cache = RenderCache()

        self.assertTrue(cache.update("timer", "09:59", rendered.append))
        self.assertFalse(cache.update("timer", "09:59", rendered.append))
        self.assertTrue(cache.update("timer", "09:58", rendered.append))

        self.assertEqual(["09:59", "09:58"], rendered)

    def test_invalidate_forces_the_next_render(self):
        rendered = []
        cache = RenderCache()
        cache.update("phase", "深度专注期", rendered.append)

        cache.invalidate()

        self.assertTrue(cache.update("phase", "深度专注期", rendered.append))
        self.assertEqual(["深度专注期", "深度专注期"], rendered)


if __name__ == "__main__":
    unittest.main()
