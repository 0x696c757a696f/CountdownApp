from __future__ import annotations

from collections.abc import Callable
import math
from typing import TypeVar


T = TypeVar("T")


def format_reminder_status(
    minimum_sec: int,
    maximum_sec: int,
    show_next_reminder: bool,
    next_reminder_remaining_sec: float | None,
) -> str:
    def minutes(seconds: int) -> str:
        value = seconds / 60
        return str(int(value)) if value.is_integer() else f"{value:.2f}".rstrip("0")

    text = f"当前随机区间：{minutes(minimum_sec)}–{minutes(maximum_sec)} 分钟"
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
