from __future__ import annotations

import ctypes
import sys
import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class DesktopBounds:
    left: int
    top: int
    width: int
    height: int


def virtual_desktop_bounds(
    get_metric: Callable[[int], int] | None = None,
) -> DesktopBounds:
    """Return the complete Windows virtual desktop, including negative origins."""
    if get_metric is None:
        if sys.platform != "win32":
            raise OSError("Virtual desktop metrics are only available on Windows")
        get_metric = ctypes.windll.user32.GetSystemMetrics
    return DesktopBounds(
        left=int(get_metric(76)),
        top=int(get_metric(77)),
        width=max(1, int(get_metric(78))),
        height=max(1, int(get_metric(79))),
    )


def _set_window_position(window_handle: int, bounds: DesktopBounds) -> None:
    user32 = ctypes.windll.user32
    shown_without_activation = 0x0040 | 0x0010
    if not user32.SetWindowPos(
        window_handle,
        -1,
        bounds.left,
        bounds.top,
        bounds.width,
        bounds.height,
        shown_without_activation,
    ):
        raise OSError(ctypes.get_last_error(), "Unable to size reminder overlay")


def cover_virtual_desktop(
    window: tk.Toplevel,
    *,
    bounds: DesktopBounds | None = None,
    native_setter: Callable[[int, DesktopBounds], None] | None = None,
) -> DesktopBounds:
    """Size a borderless Tk window across every monitor on Windows."""
    if bounds is None:
        try:
            bounds = virtual_desktop_bounds()
        except OSError:
            bounds = DesktopBounds(
                0, 0, window.winfo_screenwidth(), window.winfo_screenheight()
            )
    window.geometry(f"{bounds.width}x{bounds.height}+0+0")
    window.update_idletasks()
    if sys.platform == "win32" or native_setter is not None:
        (native_setter or _set_window_position)(window.winfo_id(), bounds)
    return bounds
