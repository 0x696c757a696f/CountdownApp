import logging
import queue
import unittest

from countdownapp.hotkeys import GlobalHotkeyService


class FakeHotkeyBackend:
    def __init__(self, rejected_ids=()):
        self.rejected_ids = set(rejected_ids)
        self.registered = []
        self.unregistered = []
        self.messages = []

    def register(self, hotkey_id, modifiers, virtual_key):
        self.registered.append((hotkey_id, modifiers, virtual_key))
        return hotkey_id not in self.rejected_ids

    def unregister(self, hotkey_id):
        self.unregistered.append(hotkey_id)

    def poll(self):
        messages, self.messages = self.messages, []
        return messages


class GlobalHotkeyServiceTests(unittest.TestCase):
    def test_registered_hotkeys_publish_commands_to_the_gui_queue(self):
        backend = FakeHotkeyBackend()
        commands = queue.Queue()
        service = GlobalHotkeyService(commands, logging.getLogger("test"), backend)

        self.assertTrue(service.start())
        backend.messages.extend([service.PAUSE_ID, service.WINDOW_ID])
        service.poll()

        self.assertTrue(service.is_active)
        self.assertEqual("pause", commands.get_nowait())
        self.assertEqual("toggle_window", commands.get_nowait())

    def test_registration_conflict_rolls_back_every_successful_binding(self):
        backend = FakeHotkeyBackend(rejected_ids={GlobalHotkeyService.WINDOW_ID})
        service = GlobalHotkeyService(queue.Queue(), logging.getLogger("test"), backend)

        self.assertFalse(service.start())

        self.assertFalse(service.is_active)
        self.assertEqual([GlobalHotkeyService.PAUSE_ID], backend.unregistered)

    def test_stop_releases_all_registered_hotkeys(self):
        backend = FakeHotkeyBackend()
        service = GlobalHotkeyService(queue.Queue(), logging.getLogger("test"), backend)
        service.start()

        service.stop()

        self.assertFalse(service.is_active)
        self.assertEqual(
            [GlobalHotkeyService.PAUSE_ID, GlobalHotkeyService.WINDOW_ID],
            backend.unregistered,
        )


if __name__ == "__main__":
    unittest.main()
