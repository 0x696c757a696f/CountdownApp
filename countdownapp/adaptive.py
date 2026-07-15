from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class AttentionFeedback(str, Enum):
    ON_TASK = "on_task"
    DISTRACTED = "distracted"
    FLOW = "flow"


@dataclass(frozen=True)
class FeedbackSummary:
    on_task_count: int = 0
    distracted_count: int = 0
    flow_count: int = 0

    @property
    def total_count(self) -> int:
        return self.on_task_count + self.distracted_count + self.flow_count


class AdaptiveReminderPolicy:
    DISTRACTED_MULTIPLIER = 0.75
    ON_TASK_MULTIPLIER = 1.25
    FLOW_MULTIPLIER = 1.5

    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled
        self._summary = FeedbackSummary()
        self._on_task_streak = 0
        self._distracted_streak = 0
        self._pending_multiplier = 1.0

    @property
    def summary(self) -> FeedbackSummary:
        return self._summary

    def record(self, feedback: AttentionFeedback) -> None:
        if not self.enabled:
            return
        if feedback is AttentionFeedback.ON_TASK:
            self._on_task_streak += 1
            self._distracted_streak = 0
            self._summary = FeedbackSummary(
                on_task_count=self._summary.on_task_count + 1,
                distracted_count=self._summary.distracted_count,
                flow_count=self._summary.flow_count,
            )
            self._pending_multiplier = (
                self.ON_TASK_MULTIPLIER if self._on_task_streak >= 3 else 1.0
            )
            return
        if feedback is AttentionFeedback.DISTRACTED:
            self._distracted_streak += 1
            self._on_task_streak = 0
            self._summary = FeedbackSummary(
                on_task_count=self._summary.on_task_count,
                distracted_count=self._summary.distracted_count + 1,
                flow_count=self._summary.flow_count,
            )
            self._pending_multiplier = (
                self.DISTRACTED_MULTIPLIER
                if self._distracted_streak >= 2
                else 1.0
            )
            return
        self._on_task_streak = 0
        self._distracted_streak = 0
        self._summary = FeedbackSummary(
            on_task_count=self._summary.on_task_count,
            distracted_count=self._summary.distracted_count,
            flow_count=self._summary.flow_count + 1,
        )
        self._pending_multiplier = self.FLOW_MULTIPLIER

    def consume_multiplier(self) -> float:
        multiplier = self._pending_multiplier
        self._pending_multiplier = 1.0
        return multiplier
