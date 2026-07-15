from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar


T = TypeVar("T")


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
