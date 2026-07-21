from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
import math
from typing import Protocol, TypeVar

from .adaptive import FeedbackSummary


T = TypeVar("T")


AMBIENT_NAMES = {
    "white": "白噪音",
    "pink": "粉红噪音",
    "brown": "棕噪音",
    "grey": "灰噪音",
    "recording:storm": "风雨雷暴",
    "recording:rain": "雨声",
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


class ScaledWindow(Protocol):
    def winfo_fpixels(self, value: str) -> float: ...


def window_ui_scale(window: ScaledWindow) -> float:
    """Return the physical-pixel scale used by a DPI-aware Tk window."""
    try:
        return max(1.0, float(window.winfo_fpixels("1i")) / 96.0)
    except (AttributeError, TypeError, ValueError):
        return 1.0


def _scaled(value: int, ui_scale: float) -> int:
    return max(1, round(value * max(1.0, ui_scale)))


def scaled_scrollbar_width(ui_scale: float) -> int:
    """Return a scrollbar width that remains easy to grab on scaled displays."""
    return max(18, _scaled(16, ui_scale))


def responsive_window_layout(
    screen_width: int,
    screen_height: int,
    *,
    ui_scale: float = 1.0,
    minimum_content_height: int = 0,
) -> WindowLayout:
    """Size and center the settings window without crowding the display edges."""
    width = min(_scaled(720, ui_scale), max(1, screen_width - _scaled(80, ui_scale)))
    height = min(
        max(690, max(0, minimum_content_height)),
        max(1, screen_height - _scaled(140, ui_scale)),
    )
    return WindowLayout(
        width=width,
        height=height,
        min_width=min(_scaled(640, ui_scale), width),
        min_height=min(540, height),
        x=max(0, (screen_width - width) // 2),
        y=max(0, (screen_height - height) // 2),
    )


def v2_window_layout(
    screen_width: int,
    screen_height: int,
    *,
    ui_scale: float = 1.0,
    minimum_content_height: int = 0,
) -> WindowLayout:
    """Size the V2 editor around its two compact settings groups."""
    width = min(_scaled(560, ui_scale), max(1, screen_width - _scaled(80, ui_scale)))
    height = min(
        max(430, max(0, minimum_content_height)),
        max(1, screen_height - _scaled(100, ui_scale)),
    )
    return WindowLayout(
        width=width,
        height=height,
        min_width=min(_scaled(540, ui_scale), width),
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
    ui_scale: float = 1.0,
) -> WindowLayout:
    """Return a compact focus window that grows only for visible audio controls."""
    preferred_height = 460 if controls_expanded else 280
    measured_height = (
        max(0, minimum_content_height) + _scaled(16, ui_scale)
        if minimum_content_height > 0
        else 0
    )
    width = min(
        _scaled(600, ui_scale),
        max(1, screen_width - _scaled(80, ui_scale)),
    )
    height = min(
        max(preferred_height, measured_height),
        max(1, screen_height - _scaled(100, ui_scale)),
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


def format_ambient_summary(sources: Sequence[str], volume: int) -> str:
    layers: list[str] = []
    for source in sources:
        if source == "off":
            continue
        if source.startswith("tone:"):
            layers.append(f"Solfeggio {source.removeprefix('tone:')} Hz")
        else:
            layers.append(AMBIENT_NAMES.get(source, source))
    if not layers:
        return "已关闭"
    bounded_volume = min(100, max(0, round(volume)))
    return f"{' + '.join(layers)} · {bounded_volume}%"


def format_feedback_summary(summary: FeedbackSummary, enabled: bool) -> str:
    if not enabled:
        return ""
    return (
        f"本轮反馈：仍在任务 {summary.on_task_count} · "
        f"走神 {summary.distracted_count} · 延后下次提醒 {summary.flow_count}"
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
