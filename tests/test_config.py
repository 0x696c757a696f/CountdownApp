import json
import tempfile
import unittest
from pathlib import Path

from countdownapp.config import AppSettings, ConfigStore
from countdownapp.domain import AlgorithmMode, ReminderPreset, SessionSettings


class ConfigStoreTests(unittest.TestCase):
    def test_first_launch_continues_with_defaults_when_config_cannot_be_written(self):
        class UnwritableStore(ConfigStore):
            def save(self, settings):
                raise PermissionError("read-only install directory")

        store = UnwritableStore(Path("unwritable") / "settings.json")

        loaded = store.migrate_legacy([])

        self.assertEqual(AppSettings(migration_completed=True), loaded)
        self.assertIsInstance(store.last_save_error, PermissionError)

    def test_new_install_uses_the_requested_default_bells(self):
        settings = AppSettings()

        self.assertEqual("0.wav", settings.audio_choice)
        self.assertEqual("1.wav", settings.return_audio_choice)

    def test_round_trips_complete_session_and_audio_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ConfigStore(Path(directory) / "settings.json")
            session = SessionSettings.defaults(
                focus_duration_sec=75 * 60,
                algorithm_mode=AlgorithmMode.V2,
            )
            expected = AppSettings(
                session=SessionSettings(
                    **{
                        **session.__dict__,
                        "reminder_preset": ReminderPreset.STRONG,
                        "break_countdown_enabled": False,
                        "adaptive_reminders_enabled": True,
                    }
                ),
                audio_choice="custom",
                custom_audio_path="D:/sounds/focus.mp3",
                return_audio_choice="custom",
                return_custom_audio_path="D:/sounds/return.mp3",
                ambient_choice="pink",
                ambient_texture_choice="recording:rain",
                solfeggio_choice="tone:639",
                ambient_volume=23,
                close_to_tray=False,
                show_next_reminder=True,
                global_hotkeys_enabled=True,
                floating_status_enabled=True,
                floating_x=-1200,
                floating_y=300,
                pause_hotkey="Ctrl+Alt+P",
                window_hotkey="Ctrl+Shift+O",
            )

            store.save(expected)
            actual = store.load()

            self.assertEqual(expected, actual)

    def test_old_v2_settings_gain_a_distinct_default_return_bell(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            store = ConfigStore(path)
            store.save(AppSettings(audio_choice="2.wav"))
            data = json.loads(path.read_text(encoding="utf-8"))
            data["audio"].pop("return_choice")
            data["audio"].pop("return_custom_path")
            data["session"].pop("break_countdown_enabled")
            data.pop("ambient")
            path.write_text(json.dumps(data), encoding="utf-8")

            loaded = store.load()

            self.assertTrue(loaded.session.break_countdown_enabled)
            self.assertTrue(loaded.close_to_tray)
            self.assertEqual("2.wav", loaded.audio_choice)
            self.assertEqual("1.wav", loaded.return_audio_choice)
            self.assertEqual("off", loaded.ambient_choice)
            self.assertEqual("off", loaded.ambient_texture_choice)
            self.assertEqual("off", loaded.solfeggio_choice)
            self.assertEqual(20, loaded.ambient_volume)

    def test_old_single_tone_selection_moves_to_the_solfeggio_layer(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            store = ConfigStore(path)
            store.save(AppSettings(ambient_choice="off"))
            data = json.loads(path.read_text(encoding="utf-8"))
            data["ambient"]["choice"] = "tone:528"
            data["ambient"].pop("solfeggio_choice")
            path.write_text(json.dumps(data), encoding="utf-8")

            loaded = store.load()

            self.assertEqual("off", loaded.ambient_choice)
            self.assertEqual("tone:528", loaded.solfeggio_choice)

    def test_old_synthetic_rain_selection_moves_to_bundled_rain_recording(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            store = ConfigStore(path)
            store.save(AppSettings(ambient_texture_choice="texture:rain"))

            loaded = store.load()

            self.assertEqual("recording:rain", loaded.ambient_texture_choice)

    def test_migrates_the_legacy_custom_audio_path_once(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            legacy = root / "settings.ini"
            legacy.write_text(
                "[AUDIO]\ncustom_audio_path = D:/sounds/legacy.wav\n",
                encoding="utf-8",
            )
            store = ConfigStore(root / "new" / "settings.json")

            migrated = store.migrate_legacy([legacy])
            legacy.write_text(
                "[AUDIO]\ncustom_audio_path = D:/sounds/changed.wav\n",
                encoding="utf-8",
            )
            loaded_again = store.migrate_legacy([legacy])

            self.assertEqual("custom", migrated.audio_choice)
            self.assertEqual("D:/sounds/legacy.wav", migrated.custom_audio_path)
            self.assertEqual(migrated, loaded_again)

    def test_missing_nested_fields_are_filled_without_discarding_user_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            store = ConfigStore(path)
            store.save(AppSettings(audio_choice="2.wav", ambient_volume=37))
            data = json.loads(path.read_text(encoding="utf-8"))
            del data["session"]["reminder_preset"]
            del data["session"]["v2"]["fatigue_interval"]
            path.write_text(json.dumps(data), encoding="utf-8")

            loaded = store.load()

            self.assertEqual("2.wav", loaded.audio_choice)
            self.assertEqual(37, loaded.ambient_volume)
            self.assertEqual(ReminderPreset.BALANCED, loaded.session.reminder_preset)
            self.assertEqual(
                SessionSettings.defaults().v2.fatigue_interval,
                loaded.session.v2.fatigue_interval,
            )

    def test_common_string_booleans_are_decoded_by_value(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            store = ConfigStore(path)
            store.save(AppSettings(close_to_tray=True, show_next_reminder=False))
            data = json.loads(path.read_text(encoding="utf-8"))
            data["behavior"]["close_to_tray"] = "false"
            data["behavior"]["show_next_reminder"] = "true"
            path.write_text(json.dumps(data), encoding="utf-8")

            loaded = store.load()

            self.assertFalse(loaded.close_to_tray)
            self.assertTrue(loaded.show_next_reminder)

    def test_schema_one_config_is_migrated_without_discarding_preferences(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            store = ConfigStore(path)
            store.save(AppSettings(audio_choice="3.wav", ambient_volume=41))
            data = json.loads(path.read_text(encoding="utf-8"))
            data["schema_version"] = 1
            path.write_text(json.dumps(data), encoding="utf-8")

            loaded = store.load()

            self.assertEqual("3.wav", loaded.audio_choice)
            self.assertEqual(41, loaded.ambient_volume)
            self.assertEqual(2, loaded.schema_version)

    def test_invalid_config_is_preserved_before_defaults_are_returned(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "settings.json"
            path.write_text("{ definitely not json", encoding="utf-8")

            store = ConfigStore(path)
            loaded = store.load()

            self.assertEqual(AppSettings(), loaded)
            self.assertFalse(path.exists())
            backups = list(root.glob("settings.invalid*.json"))
            self.assertEqual(1, len(backups))
            self.assertEqual(backups[0], store.last_recovery_path)
            self.assertEqual("{ definitely not json", backups[0].read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
