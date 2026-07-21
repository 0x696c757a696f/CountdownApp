from __future__ import annotations

import ctypes
import sys
import tkinter as tk
from collections.abc import Callable
from ctypes import wintypes
from dataclasses import dataclass
from typing import Protocol

from . import APP_NAME


@dataclass(frozen=True)
class WorkArea:
    left: int
    top: int
    right: int
    bottom: int


def fit_window_position(
    x: int,
    y: int,
    width: int,
    height: int,
    work_area: WorkArea,
    margin: int = 8,
) -> tuple[int, int]:
    minimum_x = work_area.left + margin
    minimum_y = work_area.top + margin
    maximum_x = max(minimum_x, work_area.right - width - margin)
    maximum_y = max(minimum_y, work_area.bottom - height - margin)
    return (
        min(maximum_x, max(minimum_x, x)),
        min(maximum_y, max(minimum_y, y)),
    )


class MonitorProvider(Protocol):
    def work_area_for_window(self, window_handle: int) -> WorkArea: ...

    def work_area_for_point(self, x: int, y: int) -> WorkArea: ...


class _MonitorInfo(ctypes.Structure):
    _fields_ = (
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
    )


class Win32MonitorProvider:
    MONITOR_DEFAULTTONEAREST = 0x00000002

    def __init__(self) -> None:
        if sys.platform != "win32":
            raise OSError("Monitor work areas are only available on Windows")
        self._user32 = ctypes.WinDLL("user32", use_last_error=True)
        self._user32.MonitorFromWindow.argtypes = (wintypes.HWND, wintypes.DWORD)
        self._user32.MonitorFromWindow.restype = wintypes.HANDLE
        self._user32.MonitorFromPoint.argtypes = (wintypes.POINT, wintypes.DWORD)
        self._user32.MonitorFromPoint.restype = wintypes.HANDLE
        self._user32.GetMonitorInfoW.argtypes = (
            wintypes.HANDLE,
            ctypes.POINTER(_MonitorInfo),
        )
        self._user32.GetMonitorInfoW.restype = wintypes.BOOL

    def work_area_for_window(self, window_handle: int) -> WorkArea:
        monitor = self._user32.MonitorFromWindow(
            window_handle, self.MONITOR_DEFAULTTONEAREST
        )
        return self._work_area(monitor)

    def work_area_for_point(self, x: int, y: int) -> WorkArea:
        monitor = self._user32.MonitorFromPoint(
            wintypes.POINT(x, y), self.MONITOR_DEFAULTTONEAREST
        )
        return self._work_area(monitor)

    def _work_area(self, monitor: int) -> WorkArea:
        info = _MonitorInfo()
        info.cbSize = ctypes.sizeof(info)
        if not monitor or not self._user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
            raise OSError(ctypes.get_last_error(), "Unable to read monitor work area")
        return WorkArea(
            info.rcWork.left,
            info.rcWork.top,
            info.rcWork.right,
            info.rcWork.bottom,
        )


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
        self._shown_for_session = False
        self._current_status: tuple[str, str] | None = None
        self._last_status: tuple[str, str] | None = None

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        if not enabled:
            self._shown_for_session = False
            self._close_view()

    def begin_session(self) -> None:
        self._close_view()
        self._suppressed_for_session = False
        self._shown_for_session = False
        self._current_status = None

    def update(self, timer_text: str, phase_text: str) -> None:
        status = (timer_text, phase_text)
        self._current_status = status
        if (
            not (self._enabled or self._shown_for_session)
            or self._suppressed_for_session
        ):
            return
        self._render(status)

    def show_for_session(self) -> bool:
        """Restore the floating timer using the latest active-session status."""
        if self._current_status is None:
            return False
        self._suppressed_for_session = False
        self._shown_for_session = True
        self._render(self._current_status)
        return True

    def _render(self, status: tuple[str, str]) -> None:
        if status == self._last_status:
            return
        if self._view is None:
            self._view = self._view_factory(self.hide_for_session)
        self._view.update(*status)
        self._last_status = status

    def hide_for_session(self) -> None:
        self._suppressed_for_session = True
        self._shown_for_session = False
        self._close_view()

    def end_session(self) -> None:
        self._close_view()
        self._suppressed_for_session = False
        self._shown_for_session = False
        self._current_status = None

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

    def __init__(
        self,
        root: tk.Misc,
        on_hide: Callable[[], None],
        initial_position: tuple[int, int] | None = None,
        on_position_changed: Callable[[int, int], None] | None = None,
        monitor_provider: MonitorProvider | None = None,
    ) -> None:
        self.root = root
        self._on_position_changed = on_position_changed
        try:
            self._monitor_provider = monitor_provider or Win32MonitorProvider()
        except OSError:
            self._monitor_provider = None
        self.window = tk.Toplevel(root)
        self.window.title(f"{APP_NAME}悬浮计时")
        self.window.overrideredirect(True)
        self.window.attributes("-topmost", True)
        self.window.attributes("-alpha", 0.94)
        self.window.configure(bg="#172033")
        self._width = self.WIDTH
        self._height = self.HEIGHT

        self.timer_label = tk.Label(
            self.window,
            text="00:00",
            font=("Microsoft YaHei UI", 22, "bold"),
            fg="#ffffff",
            bg="#172033",
        )
        timer_y = 6
        self.timer_label.place(x=16, y=timer_y)
        self.phase_label = tk.Label(
            self.window,
            text="",
            font=("Microsoft YaHei UI", 9),
            fg="#a8b3cf",
            bg="#172033",
        )
        self.window.update_idletasks()
        phase_y = timer_y + self.timer_label.winfo_reqheight() + 2
        self.phase_label.place(x=18, y=phase_y)
        self.window.update_idletasks()
        self._height = max(
            self.HEIGHT,
            phase_y + self.phase_label.winfo_reqheight() + 8,
        )
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
        close_button.place(x=self._width - 38, y=7, width=28, height=28)

        x, y = self._initial_position(initial_position)
        self._set_geometry(x, y, include_size=True)

        self._drag_origin: tuple[int, int] | None = None
        for widget in (self.window, self.timer_label, self.phase_label):
            widget.bind("<ButtonPress-1>", self._start_drag)
            widget.bind("<B1-Motion>", self._drag)
            widget.bind("<ButtonRelease-1>", self._finish_drag)
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
        self._set_geometry(event.x_root - offset_x, event.y_root - offset_y)

    def _finish_drag(self, _event: tk.Event) -> None:
        if self._drag_origin is None:
            return
        self._drag_origin = None
        x, y = self._fit_to_nearest_monitor(self.window.winfo_x(), self.window.winfo_y())
        self._set_geometry(x, y)
        if self._on_position_changed is not None:
            self._on_position_changed(x, y)

    def _initial_position(
        self, initial_position: tuple[int, int] | None
    ) -> tuple[int, int]:
        if initial_position is not None:
            return self._fit_to_nearest_monitor(*initial_position)
        area = self._work_area_for_window()
        return fit_window_position(
            area.right - self._width - 24,
            area.bottom - self._height - 24,
            self._width,
            self._height,
            area,
        )

    def _fit_to_nearest_monitor(self, x: int, y: int) -> tuple[int, int]:
        area = self._work_area_for_point(x, y)
        return fit_window_position(x, y, self._width, self._height, area)

    def _work_area_for_window(self) -> WorkArea:
        if self._monitor_provider is not None:
            try:
                return self._monitor_provider.work_area_for_window(self.root.winfo_id())
            except OSError:
                pass
        return self._virtual_root_area()

    def _work_area_for_point(self, x: int, y: int) -> WorkArea:
        if self._monitor_provider is not None:
            try:
                return self._monitor_provider.work_area_for_point(x, y)
            except OSError:
                pass
        return self._virtual_root_area()

    def _virtual_root_area(self) -> WorkArea:
        left = self.root.winfo_vrootx()
        top = self.root.winfo_vrooty()
        return WorkArea(
            left,
            top,
            left + self.root.winfo_vrootwidth(),
            top + self.root.winfo_vrootheight(),
        )

    def _set_geometry(self, x: int, y: int, include_size: bool = False) -> None:
        prefix = f"{self._width}x{self._height}" if include_size else ""
        self.window.geometry(f"{prefix}{x:+d}{y:+d}")
