import tkinter as tk
import unittest

from countdownapp.floating import (
    FloatingStatusController,
    TkFloatingStatusView,
    WorkArea,
    configure_floating_tool_window,
    fit_window_position,
)


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

    def test_hidden_view_can_be_restored_with_the_latest_session_status(self):
        factory = ViewFactory()
        controller = FloatingStatusController(factory)
        controller.set_enabled(True)
        controller.begin_session()
        controller.update("25:00", "注意力锚定期")

        factory.views[0].on_hide()
        controller.update("24:59", "注意力锚定期")

        self.assertTrue(controller.show_for_session())
        self.assertEqual(2, len(factory.views))
        self.assertEqual(
            [("24:59", "注意力锚定期")],
            factory.views[1].updates,
        )


class FloatingPositionTests(unittest.TestCase):
    def test_windows_floating_status_is_configured_as_a_tool_window(self):
        class Window:
            def __init__(self):
                self.events = []

            def attributes(self, name, value):
                self.events.append((name, value))

        window = Window()

        configured = configure_floating_tool_window(
            window,
            platform_name="win32",
        )

        self.assertTrue(configured)
        self.assertEqual([("-toolwindow", True)], window.events)

    def test_keeps_a_visible_position_on_a_monitor_with_negative_coordinates(self):
        area = WorkArea(-1920, 0, 0, 1040)

        position = fit_window_position(-1200, 300, 280, 82, area)

        self.assertEqual((-1200, 300), position)

    def test_clamps_an_old_position_after_its_monitor_is_removed(self):
        area = WorkArea(0, 0, 1920, 1040)

        position = fit_window_position(5000, -100, 280, 82, area)

        self.assertEqual((1632, 8), position)


class FloatingStatusLayoutTests(unittest.TestCase):
    def test_floating_window_receives_the_application_icon(self):
        try:
            root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f"Tk is unavailable: {error}")
        try:
            icon_windows = []
            view = TkFloatingStatusView(
                root,
                lambda: None,
                apply_icon=icon_windows.append,
            )

            self.assertEqual([view.window], icon_windows)
            view.close()
        finally:
            root.destroy()

    def test_high_dpi_timer_and_phase_text_do_not_overlap_or_clip(self):
        try:
            root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f"Tk is unavailable: {error}")
        old_scaling = float(root.tk.call("tk", "scaling"))
        try:
            root.tk.call("tk", "scaling", 168 / 72)

            class Monitor:
                @staticmethod
                def work_area_for_window(_window_handle):
                    return WorkArea(0, 0, 1920, 1040)

                @staticmethod
                def work_area_for_point(_x, _y):
                    return WorkArea(0, 0, 1920, 1040)

            view = TkFloatingStatusView(root, lambda: None, monitor_provider=Monitor())
            view.update("89:52", "注意力锚定期")
            root.update()
            timer_bottom = view.timer_label.winfo_y() + view.timer_label.winfo_height()
            phase_top = view.phase_label.winfo_y()
            phase_bottom = phase_top + view.phase_label.winfo_height()

            self.assertLessEqual(timer_bottom + 2, phase_top)
            self.assertLessEqual(phase_bottom + 8, view.window.winfo_height())
        finally:
            root.tk.call("tk", "scaling", old_scaling)
            root.destroy()


if __name__ == "__main__":
    unittest.main()
