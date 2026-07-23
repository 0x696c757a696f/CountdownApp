from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class AlgorithmMode(str, Enum):
    CLASSIC = "classic"
    V2 = "v2"


class ReminderPreset(str, Enum):
    BALANCED = "balanced"
    STRONG = "strong"


class SessionState(str, Enum):
    IDLE = "idle"
    FOCUSING = "focusing"
    PAUSED = "paused"
    BREAK_PROMPT = "break_prompt"
    LONG_BREAK = "long_break"
    SHUTTING_DOWN = "shutting_down"


class V2Phase(str, Enum):
    ATTENTION_ANCHOR = "attention_anchor"
    DEEP_FOCUS = "deep_focus"
    FATIGUE_SUPPORT = "fatigue_support"


@dataclass(frozen=True)
class IntervalRange:
    minimum_sec: int
    maximum_sec: int


@dataclass(frozen=True)
class V2Settings:
    anchor_end_sec: int
    fatigue_start_sec: int
    anchor_interval: IntervalRange = field(
        default_factory=lambda: IntervalRange(4 * 60, 7 * 60)
    )
    deep_focus_interval: IntervalRange = field(
        default_factory=lambda: IntervalRange(10 * 60, 15 * 60)
    )
    fatigue_interval: IntervalRange = field(
        default_factory=lambda: IntervalRange(5 * 60, 8 * 60)
    )


@dataclass(frozen=True)
class SessionSettings:
    focus_duration_sec: int
    algorithm_mode: AlgorithmMode
    classic_interval: IntervalRange
    v2: V2Settings
    reminder_preset: ReminderPreset = ReminderPreset.BALANCED
    microbreak_duration_sec: int = 10
    break_countdown_enabled: bool = True
    classic_fullscreen_reminders_enabled: bool = False
    v2_fatigue_fullscreen_reminders_enabled: bool = False
    long_break_duration_sec: int = 20 * 60
    adaptive_reminders_enabled: bool = False

    @classmethod
    def defaults(
        cls,
        focus_duration_sec: int = 90 * 60,
        algorithm_mode: AlgorithmMode | None = None,
    ) -> "SessionSettings":
        if algorithm_mode is None:
            algorithm_mode = (
                AlgorithmMode.V2
                if focus_duration_sec >= 60 * 60
                else AlgorithmMode.CLASSIC
            )
        return cls(
            focus_duration_sec=focus_duration_sec,
            algorithm_mode=algorithm_mode,
            classic_interval=IntervalRange(3 * 60, 5 * 60),
            v2=V2Settings(
                anchor_end_sec=focus_duration_sec // 3,
                fatigue_start_sec=focus_duration_sec * 13 // 18,
            ),
        )


def validate_settings(settings: SessionSettings) -> list[str]:
    errors: list[str] = []
    if settings.focus_duration_sec <= 0:
        errors.append("总专注时长必须大于 0。")
    if settings.algorithm_mode is AlgorithmMode.V2 and settings.focus_duration_sec < 15 * 60:
        errors.append("V2 模式要求专注时长至少为 15 分钟。")

    ranges = [("Classic 随机间隔", settings.classic_interval)]
    if settings.algorithm_mode is AlgorithmMode.V2:
        ranges.extend(
            [
                ("锚定期随机间隔", settings.v2.anchor_interval),
                ("深度专注期随机间隔", settings.v2.deep_focus_interval),
                ("疲劳维护期随机间隔", settings.v2.fatigue_interval),
            ]
        )
    for label, interval in ranges:
        if interval.minimum_sec <= 0 or interval.maximum_sec <= 0:
            errors.append(f"{label}必须大于 0。")
        elif interval.minimum_sec > interval.maximum_sec:
            errors.append(f"{label}的最小值不能大于最大值。")

    if settings.algorithm_mode is AlgorithmMode.V2 and not (
        0
        < settings.v2.anchor_end_sec
        < settings.v2.fatigue_start_sec
        < settings.focus_duration_sec
    ):
        errors.append("V2 阶段边界必须严格递增并位于总时长内。")
    if settings.microbreak_duration_sec <= 0:
        errors.append("微休息时长必须大于 0。")
    if settings.long_break_duration_sec <= 0:
        errors.append("大休息时长必须大于 0。")
    return errors


def reminder_coverage_warnings(settings: SessionSettings) -> list[str]:
    """Describe valid schedules whose random range may yield no reminder."""

    def warning_for(
        label: str, duration_sec: int, interval: IntervalRange
    ) -> str | None:
        duration_minutes = f"{duration_sec / 60:.1f}".rstrip("0").rstrip(".")
        if duration_sec <= interval.minimum_sec:
            return (
                f"{label}约 {duration_minutes} 分钟，不长于最小随机间隔，"
                "不会产生随机提醒。"
            )
        if duration_sec <= interval.maximum_sec:
            return (
                f"{label}约 {duration_minutes} 分钟，短于最大随机间隔，"
                "本轮可能没有提醒。"
            )
        return None

    if settings.algorithm_mode is AlgorithmMode.CLASSIC:
        warning = warning_for(
            "本次专注", settings.focus_duration_sec, settings.classic_interval
        )
        return [warning] if warning else []

    phases = (
        (
            "注意力锚定期",
            settings.v2.anchor_end_sec,
            settings.v2.anchor_interval,
        ),
        (
            "深度专注期",
            settings.v2.fatigue_start_sec - settings.v2.anchor_end_sec,
            settings.v2.deep_focus_interval,
        ),
        (
            "疲劳维护期",
            settings.focus_duration_sec - settings.v2.fatigue_start_sec,
            settings.v2.fatigue_interval,
        ),
    )
    return [
        warning
        for label, duration, interval in phases
        if (warning := warning_for(label, duration, interval)) is not None
    ]
