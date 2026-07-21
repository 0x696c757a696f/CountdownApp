from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

from .adaptive import AttentionFeedback
from .domain import IntervalRange, SessionSettings, SessionState, V2Phase
from .presentation import format_feedback_summary, format_reminder_status
from .runtime_view import RuntimeDisplay
from .scheduler import RandomSource
from .session import FocusSession, RuntimeEvent


PHASE_NAMES = {
    None: "经典随机",
    V2Phase.ATTENTION_ANCHOR: "注意力锚定期",
    V2Phase.DEEP_FOCUS: "深度专注期",
    V2Phase.FATIGUE_SUPPORT: "疲劳维护期",
}


@dataclass(frozen=True)
class FocusUpdate:
    events: tuple[RuntimeEvent, ...]
    display: RuntimeDisplay | None
    should_continue: bool
    long_break: bool = False


@dataclass(frozen=True)
class PauseTransition:
    paused: bool
    long_break: bool
    reminder_was_visible: bool
    display: RuntimeDisplay


class FocusCoordinator:
    """Owns a focus session and projects it into GUI-neutral runtime data."""

    def __init__(self, random_source: RandomSource, clock: Callable[[], float]) -> None:
        self._random_source = random_source
        self._clock = clock
        self._session: FocusSession | None = None
        self._generation = 0
        self._show_next_reminder = False

    @property
    def display(self) -> RuntimeDisplay:
        if self._session is None:
            raise RuntimeError("No focus session has started")
        return (
            self._long_break_display()
            if self._session.is_long_break
            else self._focus_display()
        )

    @property
    def state(self) -> SessionState:
        return self._session.state if self._session is not None else SessionState.IDLE

    @property
    def generation(self) -> int:
        return self._generation

    @property
    def settings(self) -> SessionSettings | None:
        return self._session.settings if self._session is not None else None

    @property
    def reminder_visible(self) -> bool:
        return bool(self._session is not None and self._session.reminder_visible)

    @property
    def is_long_break(self) -> bool:
        return bool(self._session is not None and self._session.is_long_break)

    @property
    def is_active(self) -> bool:
        return self.state not in {SessionState.IDLE, SessionState.SHUTTING_DOWN}

    def start(self, settings: SessionSettings, show_next_reminder: bool) -> int:
        self._generation += 1
        self._show_next_reminder = show_next_reminder
        self._session = FocusSession(settings, self._random_source, self._clock)
        self._session.start()
        return self._generation

    def tick(self, generation: int) -> FocusUpdate | None:
        if generation != self._generation or self._session is None:
            return None
        events = tuple(self._session.tick())
        should_continue = self._session.state not in {
            SessionState.IDLE,
            SessionState.BREAK_PROMPT,
            SessionState.SHUTTING_DOWN,
        }
        long_break = self._session.is_long_break
        display = self.display if should_continue else None
        return FocusUpdate(events, display, should_continue, long_break)

    def toggle_pause(self) -> PauseTransition | None:
        if self._session is None:
            return None
        long_break = self._session.is_long_break
        reminder_was_visible = self._session.reminder_visible
        if self._session.state in {SessionState.FOCUSING, SessionState.LONG_BREAK}:
            self._session.pause()
            paused = True
        elif self._session.state is SessionState.PAUSED:
            self._session.resume()
            paused = False
        else:
            return None
        return PauseTransition(
            paused,
            long_break,
            reminder_was_visible,
            self.display,
        )

    def start_long_break(self, duration_sec: int) -> RuntimeDisplay:
        if self._session is None:
            raise RuntimeError("No focus session has started")
        self._session.start_long_break(duration_sec)
        return self.display

    def dismiss_reminder(self) -> None:
        if self._session is not None:
            self._session.dismiss_reminder()

    def record_feedback(self, feedback: AttentionFeedback) -> bool:
        return bool(
            self._session is not None and self._session.record_feedback(feedback)
        )

    def stop(self) -> None:
        self._generation += 1
        if self._session is not None:
            self._session.stop()
            self._session = None

    def shutdown(self) -> None:
        self._generation += 1
        if self._session is not None:
            self._session.shutdown()

    def _focus_display(self) -> RuntimeDisplay:
        assert self._session is not None
        timer_text = self._format_seconds(self._session.remaining_sec)
        phase = self._session.current_phase
        state_suffix = (
            "（已暂停）" if self._session.state is SessionState.PAUSED else ""
        )
        interval = self._phase_interval(phase)
        return RuntimeDisplay(
            timer_text,
            f"{PHASE_NAMES[phase]}{state_suffix}",
            format_reminder_status(
                interval.minimum_sec,
                interval.maximum_sec,
                self._show_next_reminder,
                self._session.next_reminder_remaining_sec,
                adaptive_enabled=(
                    self._session.settings.adaptive_reminders_enabled
                ),
            ),
            format_feedback_summary(
                self._session.feedback_summary,
                self._session.settings.adaptive_reminders_enabled,
            ),
        )

    def _phase_interval(self, phase: V2Phase | None) -> IntervalRange:
        assert self._session is not None
        settings = self._session.settings
        if phase is None:
            return settings.classic_interval
        if phase is V2Phase.ATTENTION_ANCHOR:
            return settings.v2.anchor_interval
        if phase is V2Phase.DEEP_FOCUS:
            return settings.v2.deep_focus_interval
        return settings.v2.fatigue_interval

    def _long_break_display(self) -> RuntimeDisplay:
        assert self._session is not None
        phase = (
            "大休息（已暂停）"
            if self._session.state is SessionState.PAUSED
            else "大休息"
        )
        return RuntimeDisplay(
            self._format_seconds(self._session.long_break_remaining_sec),
            phase,
            "休息期间不会产生随机提醒",
        )

    @staticmethod
    def _format_seconds(seconds: float) -> str:
        value = max(0, math.ceil(seconds))
        return f"{value // 60:02d}:{value % 60:02d}"
