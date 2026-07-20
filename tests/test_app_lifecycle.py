import unittest
from unittest.mock import Mock, patch

import countdownapp.app as app_module


class RootStub:
    def __init__(self):
        self.report_callback_exception = None
        self.destroyed = False

    def mainloop(self):
        return None

    def destroy(self):
        self.destroyed = True


class ApplicationLifecycleTests(unittest.TestCase):
    def test_duplicate_launch_exits_before_creating_tk(self):
        guard = Mock()
        guard.acquire.return_value = False

        with (
            patch.object(app_module, "SingleInstanceGuard", return_value=guard),
            patch.object(app_module, "show_native_message") as show_message,
            patch.object(app_module.tk, "Tk") as create_root,
        ):
            app_module.run()

        create_root.assert_not_called()
        show_message.assert_called_once()

    def test_fatal_startup_error_is_logged_and_shown(self):
        guard = Mock()
        guard.acquire.return_value = True
        root = RootStub()
        logger = Mock()

        with (
            patch.object(app_module, "SingleInstanceGuard", return_value=guard),
            patch.object(app_module, "configure_logging", return_value=logger),
            patch.object(app_module, "configure_dpi_awareness"),
            patch.object(app_module, "configure_process_identity"),
            patch.object(app_module, "show_native_message") as show_message,
            patch.object(app_module.tk, "Tk", return_value=root),
            patch.object(app_module, "CountdownApp", side_effect=RuntimeError("boom")),
        ):
            app_module.run()

        logger.exception.assert_called_once()
        show_message.assert_called_once()
        self.assertTrue(root.destroyed)
        guard.release.assert_called_once()


if __name__ == "__main__":
    unittest.main()
