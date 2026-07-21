import queue
import unittest
from pathlib import Path
from unittest.mock import Mock

from countdownapp.tray import TrayService


class TrayServiceTests(unittest.TestCase):
    def test_floating_timer_action_is_visible_only_during_a_focus_session(self):
        service = TrayService(Path("clock_icon.png"), queue.Queue(), Mock())
        service.icon = Mock()

        self.assertFalse(service.is_floating_timer_action_visible(None))

        service.set_focus_active(True)

        self.assertTrue(service.is_floating_timer_action_visible(None))
        service.icon.update_menu.assert_called_once_with()

        service.set_focus_active(False)

        self.assertFalse(service.is_floating_timer_action_visible(None))
        self.assertEqual(2, service.icon.update_menu.call_count)


if __name__ == "__main__":
    unittest.main()
