from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable

from .domain import SessionSettings, SessionState, V2Phase, validate_settings
from .scheduler import EventKind, RandomSource, ReminderScheduler, ScheduledEvent


class RuntimeEventKind(str, Enum):
    REMINDER_DUE = "reminder_due"
    PHASE_CHANGED = "phase_changed"
    SESSION_FINISHED = "session_finished"
    SUSPEND_DETECTED = "suspend_detected"
    LONG_BREAK_FINISHED = "long_break_finished"


@dataclass(frozen=True)
class RuntimeEvent:
    kind: RuntimeEventKind
    phase: V2Phase | None = None


class FocusSession:
    """Owns focus-session time and state without depending on a GUI."""

    SUSPEND_THRESHOLD_SEC = 10.0

    def __init__(
        self,
        settings: SessionSettings,
        random_source: RandomSource,
        clock: Callable[[], float],
    ):
        errors = validate_settings(settings)
        if errors:
            raise ValueError("\n".join(errors))
        self.settings = settings
        self._clock = clock
        self._scheduler = ReminderScheduler(settings, random_source)
        self.state = SessionState.IDLE
        self.active_elapsed_sec = 0.0
        self.reminder_visible = False
        self._last_tick: float | None = None
        self._scheduled: ScheduledEvent | None = None
        self._long_break_remaining_sec: float | None = None
        self._paused_from: SessionState | None = None

    @property
    def remaining_sec(self) -> float:
        return max(0.0, self.settings.focus_duration_sec - self.active_elapsed_sec)

    @property
    def current_phase(self) -> V2Phase | None:
        return self._scheduler.phase_at(self.active_elapsed_sec)

    @property
    def next_reminder_remaining_sec(self) -> float | None:
        if self._scheduled is None or self._scheduled.kind is not EventKind.REMINDER_DUE:
            return None
        return max(0.0, self._scheduled.due_active_sec - self.active_elapsed_sec)

    @property
    def long_break_remaining_sec(self) -> float:
        return max(0.0, self._long_break_remaining_sec or 0.0)

    @property
    def is_long_break(self) -> bool:
        return self.state is SessionState.LONG_BREAK or (
            self.state is SessionState.PAUSED
            and self._paused_from is SessionState.LONG_BREAK
        )

    def start(self) -> None:
        self.state = SessionState.FOCUSING
        self.active_elapsed_sec = 0.0
        self.reminder_visible = False
        self._last_tick = self._clock()
        self._scheduled = self._scheduler.next_event(0.0)
        self._paused_from = None

    def tick(self) -> list[RuntimeEvent]:
        now = self._clock()
        if self.state is SessionState.LONG_BREAK:
            if self._last_tick is None:
                self._last_tick = now
                return []
            delta = max(0.0, now - self._last_tick)
            self._last_tick = now
            self._long_break_remaining_sec = max(
                0.0, self.long_break_remaining_sec - delta
            )
            if self._long_break_remaining_sec <= 0:
                self.state = SessionState.IDLE
                self._last_tick = None
                return [RuntimeEvent(RuntimeEventKind.LONG_BREAK_FINISHED)]
            return []
        if self.state is not SessionState.FOCUSING:
            return []
        if self._last_tick is None:
            self._last_tick = now
            return []

        delta = max(0.0, now - self._last_tick)
        self._last_tick = now
        if delta > self.SUSPEND_THRESHOLD_SEC:
            self._paused_from = SessionState.FOCUSING
            self.state = SessionState.PAUSED
            self.reminder_visible = False
            self._scheduled = None
            return [RuntimeEvent(RuntimeEventKind.SUSPEND_DETECTED, self.current_phase)]

        self.active_elapsed_sec += delta
        if self.active_elapsed_sec >= self.settings.focus_duration_sec:
            self.active_elapsed_sec = float(self.settings.focus_duration_sec)
            self.state = SessionState.BREAK_PROMPT
            self.reminder_visible = False
            self._scheduled = None
            return [RuntimeEvent(RuntimeEventKind.SESSION_FINISHED, self.current_phase)]

        if self.reminder_visible:
            return []

        events: list[RuntimeEvent] = []
        while self._scheduled and self.active_elapsed_sec >= self._scheduled.due_active_sec:
            scheduled = self._scheduled
            if scheduled.kind is EventKind.PHASE_CHANGED:
                events.append(RuntimeEvent(RuntimeEventKind.PHASE_CHANGED, self.current_phase))
                self._scheduled = self._scheduler.next_event(scheduled.due_active_sec)
                continue
            if scheduled.kind is EventKind.REMINDER_DUE:
                self.reminder_visible = True
                self._scheduled = None
                events.append(RuntimeEvent(RuntimeEventKind.REMINDER_DUE, scheduled.phase))
                break
            self.active_elapsed_sec = float(self.settings.focus_duration_sec)
            self.state = SessionState.BREAK_PROMPT
            self._scheduled = None
            events.append(RuntimeEvent(RuntimeEventKind.SESSION_FINISHED, scheduled.phase))
            break
        return events

    def pause(self) -> None:
        if self.state is SessionState.LONG_BREAK:
            now = self._clock()
            if self._last_tick is not None:
                self._long_break_remaining_sec = max(
                    0.0, self.long_break_remaining_sec - max(0.0, now - self._last_tick)
                )
            self._last_tick = now
            self._paused_from = SessionState.LONG_BREAK
            self.state = SessionState.PAUSED
            return
        if self.state is not SessionState.FOCUSING:
            return
        now = self._clock()
        if self._last_tick is not None:
            delta = max(0.0, now - self._last_tick)
            if delta <= self.SUSPEND_THRESHOLD_SEC:
                self.active_elapsed_sec = min(
                    float(self.settings.focus_duration_sec),
                    self.active_elapsed_sec + delta,
                )
        self._last_tick = now
        self._paused_from = SessionState.FOCUSING
        self.state = SessionState.PAUSED

    def start_long_break(self, duration_sec: int) -> None:
        if self.state is not SessionState.BREAK_PROMPT:
            raise RuntimeError("Long break can only start after focus finishes")
        if duration_sec <= 0:
            raise ValueError("Long break duration must be positive")
        self.state = SessionState.LONG_BREAK
        self._long_break_remaining_sec = float(duration_sec)
        self._last_tick = self._clock()
        self._paused_from = None

    def resume(self) -> None:
        if self.state is not SessionState.PAUSED:
            return
        resumed_state = self._paused_from or SessionState.FOCUSING
        self._last_tick = self._clock()
        self.state = resumed_state
        self._paused_from = None
        if (
            resumed_state is SessionState.FOCUSING
            and self._scheduled is None
            and not self.reminder_visible
        ):
            self._scheduled = self._scheduler.next_event(self.active_elapsed_sec)

    def dismiss_reminder(self) -> None:
        if not self.reminder_visible:
            return
        self.reminder_visible = False
        if self.state is SessionState.FOCUSING:
            self._scheduled = self._scheduler.next_event(self.active_elapsed_sec)

    def stop(self) -> None:
        self.state = SessionState.IDLE
        self.reminder_visible = False
        self._scheduled = None
        self._last_tick = None
        self._long_break_remaining_sec = None
        self._paused_from = None

    def shutdown(self) -> None:
        self.state = SessionState.SHUTTING_DOWN
        self.reminder_visible = False
        self._scheduled = None
        self._last_tick = None
        self._long_break_remaining_sec = None
        self._paused_from = None
