import unittest

from countdownapp.floating import FloatingStatusController


class FakeView:
    def __init__(self, on_hide):
        self.on_hide = on_hide
        self.updates = []
        self.closed = False

    def update(self, timer_text, phase_text):
        self.updates.append((timer_text, phase_text))

    def close(self):
        self.closed = True


class ViewFactory:
    def __init__(self):
        self.views = []

    def __call__(self, on_hide):
        view = FakeView(on_hide)
        self.views.append(view)
        return view


class FloatingStatusControllerTests(unittest.TestCase):
    def test_disabled_controller_does_not_create_a_window(self):
        factory = ViewFactory()
        controller = FloatingStatusController(factory)

        controller.begin_session()
        controller.update("25:00", "深度专注期")

        self.assertEqual([], factory.views)

    def test_enabled_controller_lazily_reuses_one_window(self):
        factory = ViewFactory()
        controller = FloatingStatusController(factory)
        controller.set_enabled(True)
        controller.begin_session()

        controller.update("25:00", "深度专注期")
        controller.update("24:59", "深度专注期")

        self.assertEqual(1, len(factory.views))
        self.assertEqual(
            [("25:00", "深度专注期"), ("24:59", "深度专注期")],
            factory.views[0].updates,
        )

    def test_unchanged_text_does_not_redraw_the_floating_window(self):
        factory = ViewFactory()
        controller = FloatingStatusController(factory)
        controller.set_enabled(True)
        controller.begin_session()

        controller.update("25:00", "深度专注期")
        controller.update("25:00", "深度专注期")

        self.assertEqual([("25:00", "深度专注期")], factory.views[0].updates)

    def test_manual_hide_lasts_until_the_next_session(self):
        factory = ViewFactory()
        controller = FloatingStatusController(factory)
        controller.set_enabled(True)
        controller.begin_session()
        controller.update("25:00", "注意力锚定期")
        first = factory.views[0]

        first.on_hide()
        controller.update("24:59", "注意力锚定期")
        self.assertTrue(first.closed)
        self.assertEqual(1, len(factory.views))

        controller.begin_session()
        controller.update("25:00", "注意力锚定期")
        self.assertEqual(2, len(factory.views))


if __name__ == "__main__":
    unittest.main()
