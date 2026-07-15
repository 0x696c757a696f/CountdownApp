from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from .domain import AlgorithmMode, IntervalRange, SessionSettings, V2Phase


class RandomSource(Protocol):
    def randint(self, minimum: int, maximum: int) -> int: ...


class EventKind(str, Enum):
    REMINDER_DUE = "reminder_due"
    PHASE_CHANGED = "phase_changed"
    SESSION_FINISHED = "session_finished"


@dataclass(frozen=True)
class ScheduledEvent:
    kind: EventKind
    due_active_sec: float
    phase: V2Phase | None = None


class ReminderScheduler:
    def __init__(self, settings: SessionSettings, random_source: RandomSource):
        self.settings = settings
        self.random_source = random_source

    def phase_at(self, active_elapsed_sec: float) -> V2Phase | None:
        if self.settings.algorithm_mode is AlgorithmMode.CLASSIC:
            return None
        if active_elapsed_sec < self.settings.v2.anchor_end_sec:
            return V2Phase.ATTENTION_ANCHOR
        if active_elapsed_sec < self.settings.v2.fatigue_start_sec:
            return V2Phase.DEEP_FOCUS
        return V2Phase.FATIGUE_SUPPORT

    def next_event(self, active_elapsed_sec: float) -> ScheduledEvent:
        if active_elapsed_sec >= self.settings.focus_duration_sec:
            return ScheduledEvent(
                EventKind.SESSION_FINISHED,
                self.settings.focus_duration_sec,
                self.phase_at(active_elapsed_sec),
            )

        phase = self.phase_at(active_elapsed_sec)
        interval = self._interval_for(phase)
        candidate = active_elapsed_sec + self.random_source.randint(
            interval.minimum_sec, interval.maximum_sec
        )

        phase_boundary = self._next_phase_boundary(phase)
        if phase_boundary is not None and candidate >= phase_boundary:
            return ScheduledEvent(EventKind.PHASE_CHANGED, phase_boundary, phase)
        if candidate >= self.settings.focus_duration_sec:
            return ScheduledEvent(
                EventKind.SESSION_FINISHED,
                self.settings.focus_duration_sec,
                phase,
            )
        return ScheduledEvent(EventKind.REMINDER_DUE, candidate, phase)

    def _interval_for(self, phase: V2Phase | None) -> IntervalRange:
        if phase is None:
            return self.settings.classic_interval
        if phase is V2Phase.ATTENTION_ANCHOR:
            return self.settings.v2.anchor_interval
        if phase is V2Phase.DEEP_FOCUS:
            return self.settings.v2.deep_focus_interval
        return self.settings.v2.fatigue_interval

    def _next_phase_boundary(self, phase: V2Phase | None) -> int | None:
        if phase is V2Phase.ATTENTION_ANCHOR:
            return self.settings.v2.anchor_end_sec
        if phase is V2Phase.DEEP_FOCUS:
            return self.settings.v2.fatigue_start_sec
        return None
