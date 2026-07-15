from __future__ import annotations

import configparser
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from .domain import (
    AlgorithmMode,
    IntervalRange,
    ReminderPreset,
    SessionSettings,
    V2Settings,
    validate_settings,
)
from .resources import install_dir


SCHEMA_VERSION = 2


@dataclass(frozen=True)
class AppSettings:
    session: SessionSettings = field(default_factory=SessionSettings.defaults)
    audio_choice: str = "0.wav"
    custom_audio_path: str = ""
    return_audio_choice: str = "1.wav"
    return_custom_audio_path: str = ""
    ambient_choice: str = "off"
    solfeggio_choice: str = "off"
    ambient_volume: int = 20
    close_to_tray: bool = True
    show_next_reminder: bool = False
    global_hotkeys_enabled: bool = False
    floating_status_enabled: bool = False
    floating_x: int | None = None
    floating_y: int | None = None
    pause_hotkey: str = "Alt+Shift+P"
    window_hotkey: str = "Alt+Shift+O"
    migration_completed: bool = False
    schema_version: int = SCHEMA_VERSION


def default_config_path() -> Path:
    return install_dir() / "settings.json"


class ConfigStore:
    def __init__(self, path: Path | None = None):
        self.path = path or default_config_path()
        self.last_recovery_path: Path | None = None
        self.last_save_error: OSError | None = None

    def load(self) -> AppSettings:
        if not self.path.exists():
            return AppSettings()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self._normalize_legacy_shape(data)
            merged = self._merge_missing(self._encode(AppSettings()), data)
            return self._decode(merged)
        except (OSError, ValueError, KeyError, TypeError):
            self.last_recovery_path = self._preserve_invalid_config()
            return AppSettings()

    def save(self, settings: AppSettings) -> None:
        errors = validate_settings(settings.session)
        if errors:
            raise ValueError("\n".join(errors))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        payload = json.dumps(
            self._encode(settings), ensure_ascii=False, indent=2, sort_keys=True
        )
        try:
            with temporary.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(payload)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        finally:
            if temporary.exists():
                temporary.unlink(missing_ok=True)

    def migrate_legacy(self, candidates: list[Path]) -> AppSettings:
        if self.path.exists():
            return self.load()
        custom_audio_path = ""
        for candidate in candidates:
            if not candidate.is_file():
                continue
            parser = configparser.ConfigParser()
            try:
                parser.read(candidate, encoding="utf-8")
                custom_audio_path = parser.get("AUDIO", "custom_audio_path", fallback="")
            except (OSError, configparser.Error):
                continue
            if custom_audio_path:
                break
        settings = AppSettings(
            audio_choice="custom" if custom_audio_path else "0.wav",
            custom_audio_path=custom_audio_path,
            migration_completed=True,
        )
        try:
            self.save(settings)
        except OSError as error:
            self.last_save_error = error
        return settings

    @staticmethod
    def _encode(settings: AppSettings) -> dict:
        session = settings.session
        return {
            "schema_version": SCHEMA_VERSION,
            "migration_completed": settings.migration_completed,
            "audio": {
                "choice": settings.audio_choice,
                "custom_path": settings.custom_audio_path,
                "return_choice": settings.return_audio_choice,
                "return_custom_path": settings.return_custom_audio_path,
            },
            "behavior": {
                "close_to_tray": settings.close_to_tray,
                "show_next_reminder": settings.show_next_reminder,
                "global_hotkeys_enabled": settings.global_hotkeys_enabled,
                "floating_status_enabled": settings.floating_status_enabled,
                "floating_x": settings.floating_x,
                "floating_y": settings.floating_y,
                "pause_hotkey": settings.pause_hotkey,
                "window_hotkey": settings.window_hotkey,
            },
            "ambient": {
                "choice": settings.ambient_choice,
                "solfeggio_choice": settings.solfeggio_choice,
                "volume": settings.ambient_volume,
            },
            "session": {
                "focus_duration_sec": session.focus_duration_sec,
                "algorithm_mode": session.algorithm_mode.value,
                "reminder_preset": session.reminder_preset.value,
                "microbreak_duration_sec": session.microbreak_duration_sec,
                "break_countdown_enabled": session.break_countdown_enabled,
                "adaptive_reminders_enabled": session.adaptive_reminders_enabled,
                "long_break_duration_sec": session.long_break_duration_sec,
                "classic_interval": {
                    "minimum_sec": session.classic_interval.minimum_sec,
                    "maximum_sec": session.classic_interval.maximum_sec,
                },
                "v2": {
                    "anchor_end_sec": session.v2.anchor_end_sec,
                    "fatigue_start_sec": session.v2.fatigue_start_sec,
                    "anchor_interval": ConfigStore._encode_range(session.v2.anchor_interval),
                    "deep_focus_interval": ConfigStore._encode_range(session.v2.deep_focus_interval),
                    "fatigue_interval": ConfigStore._encode_range(session.v2.fatigue_interval),
                },
            },
        }

    @staticmethod
    def _encode_range(interval: IntervalRange) -> dict:
        return {
            "minimum_sec": interval.minimum_sec,
            "maximum_sec": interval.maximum_sec,
        }

    @staticmethod
    def _decode(data: dict) -> AppSettings:
        if int(data.get("schema_version", 0)) != SCHEMA_VERSION:
            raise ValueError("Unsupported settings schema")
        raw_session = data["session"]
        raw_v2 = raw_session["v2"]

        def decode_range(raw: dict) -> IntervalRange:
            return IntervalRange(int(raw["minimum_sec"]), int(raw["maximum_sec"]))

        session = SessionSettings(
            focus_duration_sec=int(raw_session["focus_duration_sec"]),
            algorithm_mode=AlgorithmMode(raw_session["algorithm_mode"]),
            reminder_preset=ReminderPreset(raw_session["reminder_preset"]),
            microbreak_duration_sec=int(raw_session["microbreak_duration_sec"]),
            break_countdown_enabled=bool(raw_session.get("break_countdown_enabled", True)),
            adaptive_reminders_enabled=bool(
                raw_session.get("adaptive_reminders_enabled", False)
            ),
            long_break_duration_sec=int(raw_session["long_break_duration_sec"]),
            classic_interval=decode_range(raw_session["classic_interval"]),
            v2=V2Settings(
                anchor_end_sec=int(raw_v2["anchor_end_sec"]),
                fatigue_start_sec=int(raw_v2["fatigue_start_sec"]),
                anchor_interval=decode_range(raw_v2["anchor_interval"]),
                deep_focus_interval=decode_range(raw_v2["deep_focus_interval"]),
                fatigue_interval=decode_range(raw_v2["fatigue_interval"]),
            ),
        )
        errors = validate_settings(session)
        if errors:
            raise ValueError("\n".join(errors))
        audio = data.get("audio", {})
        behavior = data.get("behavior", {})
        ambient = data.get("ambient", {})
        ambient_choice = str(ambient.get("choice", "off"))
        solfeggio_choice = str(ambient.get("solfeggio_choice", "off"))
        if "solfeggio_choice" not in ambient and ambient_choice.startswith("tone:"):
            solfeggio_choice = ambient_choice
            ambient_choice = "off"

        def optional_int(value: object) -> int | None:
            return None if value is None else int(value)

        return AppSettings(
            session=session,
            audio_choice=str(audio.get("choice", "0.wav")),
            custom_audio_path=str(audio.get("custom_path", "")),
            return_audio_choice=str(audio.get("return_choice", "1.wav")),
            return_custom_audio_path=str(audio.get("return_custom_path", "")),
            ambient_choice=ambient_choice,
            solfeggio_choice=solfeggio_choice,
            ambient_volume=max(0, min(100, int(ambient.get("volume", 20)))),
            close_to_tray=bool(behavior.get("close_to_tray", True)),
            show_next_reminder=bool(behavior.get("show_next_reminder", False)),
            global_hotkeys_enabled=bool(
                behavior.get("global_hotkeys_enabled", False)
            ),
            floating_status_enabled=bool(
                behavior.get("floating_status_enabled", False)
            ),
            floating_x=optional_int(behavior.get("floating_x")),
            floating_y=optional_int(behavior.get("floating_y")),
            pause_hotkey=str(behavior.get("pause_hotkey", "Alt+Shift+P")),
            window_hotkey=str(behavior.get("window_hotkey", "Alt+Shift+O")),
            migration_completed=bool(data.get("migration_completed", False)),
            schema_version=SCHEMA_VERSION,
        )

    @staticmethod
    def _merge_missing(defaults: dict, user_data: dict) -> dict:
        if not isinstance(user_data, dict):
            raise TypeError("Settings root must be an object")
        merged = dict(defaults)
        for key, value in user_data.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = ConfigStore._merge_missing(merged[key], value)
            else:
                merged[key] = value
        return merged

    @staticmethod
    def _normalize_legacy_shape(data: dict) -> None:
        if not isinstance(data, dict):
            return
        ambient = data.get("ambient")
        if not isinstance(ambient, dict) or "solfeggio_choice" in ambient:
            return
        choice = ambient.get("choice")
        if isinstance(choice, str) and choice.startswith("tone:"):
            ambient["solfeggio_choice"] = choice
            ambient["choice"] = "off"

    def _preserve_invalid_config(self) -> Path | None:
        if not self.path.exists():
            return None
        candidate = self.path.with_name(f"{self.path.stem}.invalid{self.path.suffix}")
        sequence = 1
        while candidate.exists():
            candidate = self.path.with_name(
                f"{self.path.stem}.invalid.{sequence}{self.path.suffix}"
            )
            sequence += 1
        try:
            os.replace(self.path, candidate)
            return candidate
        except OSError:
            return None
