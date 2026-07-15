import unittest

from countdownapp.startup import (
    StartupManager,
    StartupMode,
    build_startup_command,
    should_start_hidden,
)


class MemoryRegistry:
    def __init__(self):
        self.values = {}

    def read(self, name):
        return self.values.get(name)

    def write(self, name, value):
        self.values[name] = value

    def delete(self, name):
        self.values.pop(name, None)


class StartupManagerTests(unittest.TestCase):
    def test_selects_visible_silent_and_disabled_startup_modes(self):
        registry = MemoryRegistry()
        manager = StartupManager(
            visible_command='"C:\\Apps\\CountdownApp.exe"',
            silent_command='"C:\\Apps\\CountdownApp.exe" --startup',
            registry=registry,
        )

        manager.set_mode(StartupMode.VISIBLE)
        self.assertEqual(StartupMode.VISIBLE, manager.get_mode())

        manager.set_mode(StartupMode.SILENT)
        self.assertEqual(StartupMode.SILENT, manager.get_mode())

        manager.set_mode(StartupMode.OFF)
        self.assertEqual(StartupMode.OFF, manager.get_mode())

    def test_startup_command_is_quoted_and_requests_hidden_start(self):
        visible = build_startup_command(
            r"C:\Program Files\CountdownApp\CountdownApp.exe", silent=False
        )
        silent = build_startup_command(
            r"C:\Program Files\CountdownApp\CountdownApp.exe", silent=True
        )

        self.assertEqual(
            '"C:\\Program Files\\CountdownApp\\CountdownApp.exe"',
            visible,
        )
        self.assertEqual(
            '"C:\\Program Files\\CountdownApp\\CountdownApp.exe" --startup',
            silent,
        )

    def test_reconcile_removes_a_stale_command_from_an_old_install(self):
        registry = MemoryRegistry()
        registry.values["CountdownApp"] = '"C:\\Old\\CountdownApp.exe" --startup'
        manager = StartupManager(
            visible_command='"C:\\New\\CountdownApp.exe"',
            silent_command='"C:\\New\\CountdownApp.exe" --startup',
            registry=registry,
        )

        self.assertEqual(StartupMode.OFF, manager.reconcile_mode())
        self.assertNotIn("CountdownApp", registry.values)

    def test_reconcile_preserves_the_current_visible_and_silent_commands(self):
        registry = MemoryRegistry()
        manager = StartupManager(
            visible_command='"C:\\Apps\\CountdownApp.exe"',
            silent_command='"C:\\Apps\\CountdownApp.exe" --startup',
            registry=registry,
        )

        manager.set_mode(StartupMode.VISIBLE)
        self.assertEqual(StartupMode.VISIBLE, manager.reconcile_mode())
        manager.set_mode(StartupMode.SILENT)
        self.assertEqual(StartupMode.SILENT, manager.reconcile_mode())

    def test_only_a_startup_launch_with_a_working_tray_starts_hidden(self):
        self.assertTrue(should_start_hidden(["app.exe", "--startup"], tray_ready=True))
        self.assertFalse(should_start_hidden(["app.exe"], tray_ready=True))
        self.assertFalse(
            should_start_hidden(["app.exe", "--startup"], tray_ready=False)
        )


if __name__ == "__main__":
    unittest.main()
