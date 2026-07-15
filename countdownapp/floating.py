from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from typing import Protocol


class FloatingStatusView(Protocol):
    def update(self, timer_text: str, phase_text: str) -> None: ...

    def close(self) -> None: ...


class FloatingStatusController:
    """Owns the lazy, per-session lifecycle of the optional floating view."""

    def __init__(
        self,
        view_factory: Callable[[Callable[[], None]], FloatingStatusView],
    ) -> None:
        self._view_factory = view_factory
        self._view: FloatingStatusView | None = None
        self._enabled = False
        self._suppressed_for_session = False
        self._last_status: tuple[str, str] | None = None

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        if not enabled:
            self._close_view()

    def begin_session(self) -> None:
        self._close_view()
        self._suppressed_for_session = False

    def update(self, timer_text: str, phase_text: str) -> None:
        if not self._enabled or self._suppressed_for_session:
            return
        status = (timer_text, phase_text)
        if status == self._last_status:
            return
        if self._view is None:
            self._view = self._view_factory(self.hide_for_session)
        self._view.update(timer_text, phase_text)
        self._last_status = status

    def hide_for_session(self) -> None:
        self._suppressed_for_session = True
        self._close_view()

    def end_session(self) -> None:
        self._close_view()
        self._suppressed_for_session = False

    def close(self) -> None:
        self._enabled = False
        self.end_session()

    def _close_view(self) -> None:
        view, self._view = self._view, None
        self._last_status = None
        if view is not None:
            view.close()


class TkFloatingStatusView:
    WIDTH = 280
    HEIGHT = 82

    def __init__(self, root: tk.Misc, on_hide: Callable[[], None]) -> None:
        self.window = tk.Toplevel(root)
        self.window.title("CountdownApp 悬浮计时")
        self.window.overrideredirect(True)
        self.window.attributes("-topmost", True)
        self.window.attributes("-alpha", 0.94)
        self.window.configure(bg="#172033")
        x = max(0, self.window.winfo_screenwidth() - self.WIDTH - 24)
        y = max(0, self.window.winfo_screenheight() - self.HEIGHT - 72)
        self.window.geometry(f"{self.WIDTH}x{self.HEIGHT}+{x}+{y}")

        self.timer_label = tk.Label(
            self.window,
            text="00:00",
            font=("Microsoft YaHei UI", 22, "bold"),
            fg="#ffffff",
            bg="#172033",
        )
        self.timer_label.place(x=16, y=8)
        self.phase_label = tk.Label(
            self.window,
            text="",
            font=("Microsoft YaHei UI", 9),
            fg="#a8b3cf",
            bg="#172033",
        )
        self.phase_label.place(x=18, y=52)
        close_button = tk.Button(
            self.window,
            text="×",
            command=on_hide,
            relief="flat",
            borderwidth=0,
            font=("Microsoft YaHei UI", 13),
            fg="#a8b3cf",
            bg="#172033",
            activeforeground="#ffffff",
            activebackground="#26324a",
        )
        close_button.place(x=self.WIDTH - 38, y=7, width=28, height=28)

        self._drag_origin: tuple[int, int] | None = None
        for widget in (self.window, self.timer_label, self.phase_label):
            widget.bind("<ButtonPress-1>", self._start_drag)
            widget.bind("<B1-Motion>", self._drag)
            widget.bind("<Button-3>", lambda _event: on_hide())

    def update(self, timer_text: str, phase_text: str) -> None:
        self.timer_label.configure(text=timer_text)
        self.phase_label.configure(text=phase_text)

    def close(self) -> None:
        try:
            self.window.destroy()
        except tk.TclError:
            pass

    def _start_drag(self, event: tk.Event) -> None:
        self._drag_origin = (event.x_root - self.window.winfo_x(), event.y_root - self.window.winfo_y())

    def _drag(self, event: tk.Event) -> None:
        if self._drag_origin is None:
            return
        offset_x, offset_y = self._drag_origin
        self.window.geometry(f"+{event.x_root - offset_x}+{event.y_root - offset_y}")
