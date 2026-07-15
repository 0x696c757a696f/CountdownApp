from __future__ import annotations

import math
import tkinter as tk
from dataclasses import replace
from pathlib import Path

from .config import AppSettings
from .domain import (
    AlgorithmMode,
    IntervalRange,
    ReminderPreset,
    SessionSettings,
    V2Settings,
    validate_settings,
)


AUDIO_OPTIONS = {
    "提示音 0": "0.wav",
    "提示音 1": "1.wav",
    "提示音 2": "2.wav",
    "提示音 3": "3.wav",
    "提示音 4": "4.mp3",
    "自定义音频": "custom",
}

NOISE_OPTIONS = {
    "关闭": "off",
    "白噪音": "white",
    "粉红噪音": "pink",
    "棕噪音（低频更强）": "brown",
    "灰噪音（近似等响度）": "grey",
}

SOLFEGGIO_OPTIONS = {
    "关闭": "off",
    "Solfeggio 174 Hz": "tone:174",
    "Solfeggio 285 Hz": "tone:285",
    "Solfeggio 396 Hz": "tone:396",
    "Solfeggio 417 Hz": "tone:417",
    "Solfeggio 528 Hz": "tone:528",
    "Solfeggio 639 Hz": "tone:639",
    "Solfeggio 741 Hz": "tone:741",
    "Solfeggio 852 Hz": "tone:852",
    "Solfeggio 963 Hz": "tone:963",
}


class SettingsForm:
    """Owns settings variables, option mapping, parsing, and validation."""

    def __init__(self, master: tk.Misc) -> None:
        self.total = tk.StringVar(master)
        self.algorithm = tk.StringVar(master)
        self.classic_min = tk.StringVar(master)
        self.classic_max = tk.StringVar(master)
        self.anchor_end = tk.StringVar(master)
        self.fatigue_start = tk.StringVar(master)
        self.anchor_min = tk.StringVar(master)
        self.anchor_max = tk.StringVar(master)
        self.deep_min = tk.StringVar(master)
        self.deep_max = tk.StringVar(master)
        self.fatigue_min = tk.StringVar(master)
        self.fatigue_max = tk.StringVar(master)
        self.preset = tk.StringVar(master)
        self.microbreak = tk.StringVar(master)
        self.break_countdown = tk.BooleanVar(master)
        self.adaptive = tk.BooleanVar(master)
        self.long_break = tk.StringVar(master)
        self.audio = tk.StringVar(master)
        self.return_audio = tk.StringVar(master)
        self.ambient = tk.StringVar(master)
        self.solfeggio = tk.StringVar(master)
        self.ambient_volume = tk.DoubleVar(master)
        self.ambient_volume_label = tk.StringVar(master)
        self.close_to_tray = tk.BooleanVar(master)
        self.show_next_reminder = tk.BooleanVar(master)
        self.global_hotkeys = tk.BooleanVar(master)
        self.floating_status = tk.BooleanVar(master)
        self.pause_hotkey = tk.StringVar(master)
        self.window_hotkey = tk.StringVar(master)
        self.custom_audio_path = ""
        self.return_custom_audio_path = ""

    def load(self, settings: AppSettings) -> None:
        session = settings.session
        self.total.set(self.format_number(session.focus_duration_sec / 60))
        self.algorithm.set(
            "V2" if session.algorithm_mode is AlgorithmMode.V2 else "Classic"
        )
        self.classic_min.set(
            self.format_number(session.classic_interval.minimum_sec / 60)
        )
        self.classic_max.set(
            self.format_number(session.classic_interval.maximum_sec / 60)
        )
        self.anchor_end.set(self.format_number(session.v2.anchor_end_sec / 60))
        self.fatigue_start.set(
            self.format_number(session.v2.fatigue_start_sec / 60)
        )
        self.anchor_min.set(
            self.format_number(session.v2.anchor_interval.minimum_sec / 60)
        )
        self.anchor_max.set(
            self.format_number(session.v2.anchor_interval.maximum_sec / 60)
        )
        self.deep_min.set(
            self.format_number(session.v2.deep_focus_interval.minimum_sec / 60)
        )
        self.deep_max.set(
            self.format_number(session.v2.deep_focus_interval.maximum_sec / 60)
        )
        self.fatigue_min.set(
            self.format_number(session.v2.fatigue_interval.minimum_sec / 60)
        )
        self.fatigue_max.set(
            self.format_number(session.v2.fatigue_interval.maximum_sec / 60)
        )
        self.preset.set(
            "强干预" if session.reminder_preset is ReminderPreset.STRONG else "平衡"
        )
        self.microbreak.set(str(session.microbreak_duration_sec))
        self.break_countdown.set(session.break_countdown_enabled)
        self.adaptive.set(session.adaptive_reminders_enabled)
        self.long_break.set(
            self.format_number(session.long_break_duration_sec / 60)
        )
        self.audio.set(self._label_for(AUDIO_OPTIONS, settings.audio_choice, "提示音 0"))
        self.custom_audio_path = settings.custom_audio_path
        self.return_audio.set(
            self._label_for(AUDIO_OPTIONS, settings.return_audio_choice, "提示音 1")
        )
        self.return_custom_audio_path = settings.return_custom_audio_path
        self.ambient.set(self._label_for(NOISE_OPTIONS, settings.ambient_choice, "关闭"))
        self.solfeggio.set(
            self._label_for(SOLFEGGIO_OPTIONS, settings.solfeggio_choice, "关闭")
        )
        self.ambient_volume.set(settings.ambient_volume)
        self.ambient_volume_label.set(f"{settings.ambient_volume}%")
        self.close_to_tray.set(settings.close_to_tray)
        self.show_next_reminder.set(settings.show_next_reminder)
        self.global_hotkeys.set(settings.global_hotkeys_enabled)
        self.floating_status.set(settings.floating_status_enabled)
        self.pause_hotkey.set(settings.pause_hotkey)
        self.window_hotkey.set(settings.window_hotkey)

    def build_session_settings(self) -> SessionSettings:
        settings = SessionSettings(
            focus_duration_sec=self.parse_minutes(self.total.get(), "总专注时间"),
            algorithm_mode=(
                AlgorithmMode.V2
                if self.algorithm.get() == "V2"
                else AlgorithmMode.CLASSIC
            ),
            classic_interval=IntervalRange(
                self.parse_minutes(self.classic_min.get(), "Classic 最小间隔"),
                self.parse_minutes(self.classic_max.get(), "Classic 最大间隔"),
            ),
            v2=V2Settings(
                anchor_end_sec=self.parse_minutes(self.anchor_end.get(), "锚定期结束"),
                fatigue_start_sec=self.parse_minutes(
                    self.fatigue_start.get(), "疲劳期开始"
                ),
                anchor_interval=IntervalRange(
                    self.parse_minutes(self.anchor_min.get(), "锚定期最小间隔"),
                    self.parse_minutes(self.anchor_max.get(), "锚定期最大间隔"),
                ),
                deep_focus_interval=IntervalRange(
                    self.parse_minutes(self.deep_min.get(), "深度期最小间隔"),
                    self.parse_minutes(self.deep_max.get(), "深度期最大间隔"),
                ),
                fatigue_interval=IntervalRange(
                    self.parse_minutes(self.fatigue_min.get(), "疲劳期最小间隔"),
                    self.parse_minutes(self.fatigue_max.get(), "疲劳期最大间隔"),
                ),
            ),
            reminder_preset=(
                ReminderPreset.STRONG
                if self.preset.get() == "强干预"
                else ReminderPreset.BALANCED
            ),
            microbreak_duration_sec=self.parse_positive_int(
                self.microbreak.get(), "微休息"
            ),
            break_countdown_enabled=self.break_countdown.get(),
            long_break_duration_sec=self.parse_minutes(
                self.long_break.get(), "大休息"
            ),
            adaptive_reminders_enabled=self.adaptive.get(),
        )
        errors = validate_settings(settings)
        if errors:
            raise ValueError("\n".join(errors))
        self._validate_custom_audio()
        return settings

    def build_app_settings(
        self, previous: AppSettings, session: SessionSettings
    ) -> AppSettings:
        return replace(
            previous,
            session=session,
            audio_choice=self.audio_value,
            custom_audio_path=self.custom_audio_path,
            return_audio_choice=self.return_audio_value,
            return_custom_audio_path=self.return_custom_audio_path,
            ambient_choice=self.ambient_value,
            solfeggio_choice=self.solfeggio_value,
            ambient_volume=round(self.ambient_volume.get()),
            close_to_tray=self.close_to_tray.get(),
            show_next_reminder=self.show_next_reminder.get(),
            global_hotkeys_enabled=self.global_hotkeys.get(),
            floating_status_enabled=self.floating_status.get(),
            pause_hotkey=self.pause_hotkey.get().strip(),
            window_hotkey=self.window_hotkey.get().strip(),
            migration_completed=True,
        )

    def reset_v2_defaults(self) -> None:
        total = self.parse_minutes(self.total.get(), "总专注时间")
        self.anchor_end.set(self.format_number(total / 3 / 60))
        self.fatigue_start.set(self.format_number(total * 13 / 18 / 60))
        self.anchor_min.set("4")
        self.anchor_max.set("7")
        self.deep_min.set("10")
        self.deep_max.set("15")
        self.fatigue_min.set("5")
        self.fatigue_max.set("8")

    @property
    def audio_value(self) -> str:
        return AUDIO_OPTIONS.get(self.audio.get(), "0.wav")

    @property
    def return_audio_value(self) -> str:
        return AUDIO_OPTIONS.get(self.return_audio.get(), "1.wav")

    @property
    def ambient_value(self) -> str:
        return NOISE_OPTIONS.get(self.ambient.get(), "off")

    @property
    def solfeggio_value(self) -> str:
        return SOLFEGGIO_OPTIONS.get(self.solfeggio.get(), "off")

    @property
    def ambient_volume_fraction(self) -> float:
        return min(1.0, max(0.0, self.ambient_volume.get() / 100.0))

    @staticmethod
    def format_number(value: float) -> str:
        return (
            str(int(value))
            if float(value).is_integer()
            else f"{value:.2f}".rstrip("0")
        )

    @staticmethod
    def parse_minutes(value: str, label: str) -> int:
        try:
            number = float(value.strip())
        except (TypeError, ValueError):
            raise ValueError(f"{label}必须是数字。") from None
        if not math.isfinite(number) or number <= 0:
            raise ValueError(f"{label}必须大于 0。")
        return max(1, round(number * 60))

    @staticmethod
    def parse_positive_int(value: str, label: str) -> int:
        try:
            number = int(value.strip())
        except (TypeError, ValueError):
            raise ValueError(f"{label}必须是整数。") from None
        if number <= 0:
            raise ValueError(f"{label}必须大于 0。")
        return number

    @staticmethod
    def _label_for(options: dict[str, str], value: str, fallback: str) -> str:
        return next((label for label, option in options.items() if option == value), fallback)

    def _validate_custom_audio(self) -> None:
        for choice, path, label in (
            (self.audio_value, self.custom_audio_path, "自定义开始铃"),
            (self.return_audio_value, self.return_custom_audio_path, "自定义回归铃"),
        ):
            if choice != "custom":
                continue
            custom = Path(path)
            if not custom.is_file() or custom.suffix.lower() not in {
                ".wav",
                ".ogg",
                ".mp3",
            }:
                raise ValueError(f"{label}不存在或格式不受支持。")
