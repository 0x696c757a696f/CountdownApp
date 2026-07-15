from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import math
from typing import TypeVar

from .adaptive import FeedbackSummary


T = TypeVar("T")


AMBIENT_NAMES = {
    "white": "白噪音",
    "pink": "粉红噪音",
    "brown": "棕噪音",
    "grey": "灰噪音",
}


@dataclass(frozen=True)
class WindowLayout:
    width: int
    height: int
    min_width: int
    min_height: int
    x: int
    y: int

    @property
    def geometry(self) -> str:
        return f"{self.width}x{self.height}+{self.x}+{self.y}"


def responsive_window_layout(screen_width: int, screen_height: int) -> WindowLayout:
    """Size and center the settings window without crowding the display edges."""
    width = min(720, max(1, screen_width - 80))
    height = min(690, max(1, screen_height - 140))
    return WindowLayout(
        width=width,
        height=height,
        min_width=min(640, width),
        min_height=min(540, height),
        x=max(0, (screen_width - width) // 2),
        y=max(0, (screen_height - height) // 2),
    )


def v2_window_layout(screen_width: int, screen_height: int) -> WindowLayout:
    """Size the V2 editor around its two compact settings groups."""
    width = min(560, max(1, screen_width - 80))
    height = min(430, max(1, screen_height - 100))
    return WindowLayout(
        width=width,
        height=height,
        min_width=min(540, width),
        min_height=min(410, height),
        x=max(0, (screen_width - width) // 2),
        y=max(0, (screen_height - height) // 2),
    )


def runtime_window_layout(
    screen_width: int,
    screen_height: int,
    *,
    controls_expanded: bool,
    minimum_content_height: int = 0,
) -> WindowLayout:
    """Return a compact focus window that grows only for visible audio controls."""
    preferred_height = 460 if controls_expanded else 280
    width = min(600, max(1, screen_width - 80))
    height = min(
        max(preferred_height, max(0, minimum_content_height)),
        max(1, screen_height - 100),
    )
    return WindowLayout(
        width=width,
        height=height,
        min_width=width,
        min_height=height,
        x=max(0, (screen_width - width) // 2),
        y=max(0, (screen_height - height) // 2),
    )


def scroll_fraction_to_reveal(
    target_y: int, content_height: int, margin: int = 24
) -> float:
    """Return a bounded canvas position that reveals an expanded section."""
    if content_height <= 0:
        return 0.0
    return min(1.0, max(0.0, (target_y - margin) / content_height))


def format_ambient_summary(noise: str, tone: str, volume: int) -> str:
    layers: list[str] = []
    if noise != "off":
        layers.append(AMBIENT_NAMES.get(noise, noise))
    if tone.startswith("tone:"):
        layers.append(f"Solfeggio {tone.removeprefix('tone:')} Hz")
    if not layers:
        return "已关闭"
    bounded_volume = min(100, max(0, round(volume)))
    return f"{' + '.join(layers)} · {bounded_volume}%"


def format_feedback_summary(summary: FeedbackSummary, enabled: bool) -> str:
    if not enabled:
        return ""
    return (
        f"本轮反馈：仍在任务 {summary.on_task_count} · "
        f"走神 {summary.distracted_count} · 心流延后 {summary.flow_count}"
    )


def format_reminder_status(
    minimum_sec: int,
    maximum_sec: int,
    show_next_reminder: bool,
    next_reminder_remaining_sec: float | None,
    adaptive_enabled: bool = False,
) -> str:
    def minutes(seconds: int) -> str:
        value = seconds / 60
        return str(int(value)) if value.is_integer() else f"{value:.2f}".rstrip("0")

    range_label = "当前基础随机区间" if adaptive_enabled else "当前随机区间"
    text = f"{range_label}：{minutes(minimum_sec)}–{minutes(maximum_sec)} 分钟"
    if adaptive_enabled:
        text = f"{text} ｜ 自适应反馈开启"
    if not show_next_reminder:
        return text
    if next_reminder_remaining_sec is None:
        return f"{text} ｜ 阶段切换后重新抽取"
    remaining = max(0, math.ceil(next_reminder_remaining_sec))
    return f"{text} ｜ 下次提醒约 {remaining // 60:02d}:{remaining % 60:02d} 后"


class RenderCache:
    """Render display values only when their observable value changes."""

    def __init__(self) -> None:
        self._values: dict[str, object] = {}

    def update(self, key: str, value: T, render: Callable[[T], None]) -> bool:
        if key in self._values and self._values[key] == value:
            return False
        self._values[key] = value
        render(value)
        return True

    def invalidate(self) -> None:
        self._values.clear()
