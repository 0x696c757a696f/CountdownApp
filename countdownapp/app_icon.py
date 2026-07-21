from __future__ import annotations

import ctypes
import sys
import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from .resources import resource_path


APP_USER_MODEL_ID = "CountdownApp.FocusTimer"
DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4
SM_CXICON = 11
SM_CXSMICON = 49
ICON_SMALL = 0
ICON_BIG = 1
IMAGE_ICON = 1
LR_LOADFROMFILE = 0x0010
WM_SETICON = 0x0080

_retained_native_icon_handles: list[int] = []


class IconWindow(Protocol):
    def iconphoto(self, default: bool, image: object) -> None: ...
    def iconbitmap(self, *, bitmap: str) -> None: ...


class NativeIconWindow(Protocol):
    def update_idletasks(self) -> None: ...
    def winfo_id(self) -> int: ...


class NativeIconApi(Protocol):
    def top_level_handle(self, child_handle: int) -> int: ...
    def dpi_for_window(self, window_handle: int) -> int: ...
    def metric_for_dpi(self, metric: int, dpi: int) -> int: ...
    def load_icon(self, path: Path, size: int) -> int: ...
    def set_icon(self, window_handle: int, kind: int, icon_handle: int) -> None: ...


class _CtypesNativeIconApi:
    def __init__(self) -> None:
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.user32.GetParent.argtypes = [ctypes.c_void_p]
        self.user32.GetParent.restype = ctypes.c_void_p
        self.user32.GetDpiForWindow.argtypes = [ctypes.c_void_p]
        self.user32.GetDpiForWindow.restype = ctypes.c_uint
        self.user32.GetSystemMetricsForDpi.argtypes = [ctypes.c_int, ctypes.c_uint]
        self.user32.GetSystemMetricsForDpi.restype = ctypes.c_int
        self.user32.LoadImageW.argtypes = [
            ctypes.c_void_p,
            ctypes.c_wchar_p,
            ctypes.c_uint,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_uint,
        ]
        self.user32.LoadImageW.restype = ctypes.c_void_p
        self.user32.SendMessageW.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint,
            ctypes.c_void_p,
            ctypes.c_void_p,
        ]
        self.user32.SendMessageW.restype = ctypes.c_ssize_t

    def top_level_handle(self, child_handle: int) -> int:
        parent = self.user32.GetParent(ctypes.c_void_p(child_handle))
        return int(parent or child_handle)

    def dpi_for_window(self, window_handle: int) -> int:
        return int(self.user32.GetDpiForWindow(ctypes.c_void_p(window_handle)))

    def metric_for_dpi(self, metric: int, dpi: int) -> int:
        return int(self.user32.GetSystemMetricsForDpi(metric, dpi))

    def load_icon(self, path: Path, size: int) -> int:
        handle = self.user32.LoadImageW(
            None,
            str(path),
            IMAGE_ICON,
            size,
            size,
            LR_LOADFROMFILE,
        )
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        return int(handle)

    def set_icon(self, window_handle: int, kind: int, icon_handle: int) -> None:
        self.user32.SendMessageW(
            ctypes.c_void_p(window_handle),
            WM_SETICON,
            ctypes.c_void_p(kind),
            ctypes.c_void_p(icon_handle),
        )


def _load_png(path: str) -> tk.PhotoImage:
    return tk.PhotoImage(file=path)


def configure_process_identity(
    *,
    platform_name: str = sys.platform,
    setter: Callable[[str], int | None] | None = None,
) -> bool:
    """Give Windows a stable identity for taskbar grouping and icon selection."""
    if platform_name != "win32":
        return False
    if setter is None:
        windows_setter = ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID
        windows_setter.argtypes = [ctypes.c_wchar_p]
        windows_setter.restype = ctypes.c_long
        setter = windows_setter
    result = setter(APP_USER_MODEL_ID)
    if result not in (None, 0):
        raise OSError(result, "Setting the Windows AppUserModelID failed")
    return True


def configure_dpi_awareness(
    *,
    platform_name: str = sys.platform,
    setter: Callable[[int], bool] | None = None,
) -> bool:
    """Enable sharp per-monitor rendering before Tk creates its first window."""
    if platform_name != "win32":
        return False
    if setter is not None:
        result = setter(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2)
    else:
        windows_setter = ctypes.windll.user32.SetProcessDpiAwarenessContext
        windows_setter.argtypes = [ctypes.c_void_p]
        windows_setter.restype = ctypes.c_bool
        result = bool(
            windows_setter(
                ctypes.c_void_p(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2)
            )
        )
    if result is False:
        raise ctypes.WinError(ctypes.get_last_error())
    return True


def apply_windows_native_icons(
    root: NativeIconWindow,
    icon_path: Path,
    *,
    native_api: NativeIconApi | None = None,
) -> tuple[int, int]:
    """Load separate physical-size HICONs for the current monitor DPI."""
    api = native_api or _CtypesNativeIconApi()
    root.update_idletasks()
    window_handle = api.top_level_handle(root.winfo_id())
    dpi = api.dpi_for_window(window_handle)
    small_size = api.metric_for_dpi(SM_CXSMICON, dpi)
    large_size = api.metric_for_dpi(SM_CXICON, dpi)
    small_icon = api.load_icon(icon_path, small_size)
    large_icon = api.load_icon(icon_path, large_size)
    api.set_icon(window_handle, ICON_SMALL, small_icon)
    api.set_icon(window_handle, ICON_BIG, large_icon)
    return small_icon, large_icon


def apply_window_icon(
    root: IconWindow,
    *,
    resolve_resource: Callable[[str], Path] = resource_path,
    image_factory: Callable[[str], object] = _load_png,
    platform_name: str = sys.platform,
    native_api: NativeIconApi | None = None,
) -> object:
    """Apply one icon family to the root and all subsequently created windows."""
    photo = image_factory(str(resolve_resource("clock_icon.png")))
    root.iconphoto(True, photo)
    icon_path = resolve_resource("clock_icon.ico")
    if platform_name == "win32":
        try:
            handles = apply_windows_native_icons(
                root,
                icon_path,
                native_api=native_api,
            )
            _retained_native_icon_handles.extend(handles)
        except (AttributeError, OSError):
            root.iconbitmap(bitmap=str(icon_path))
    else:
        try:
            root.iconbitmap(bitmap=str(icon_path))
        except tk.TclError:
            # PNG remains the portable icon source on platforms without ICO support.
            pass
    return photo


def apply_child_window_icon(
    window: IconWindow,
    photo: object,
    *,
    resolve_resource: Callable[[str], Path] = resource_path,
    platform_name: str = sys.platform,
    native_api: NativeIconApi | None = None,
) -> None:
    """Apply the already loaded icon family to an independent child window."""
    window.iconphoto(False, photo)
    icon_path = resolve_resource("clock_icon.ico")
    if platform_name == "win32":
        try:
            handles = apply_windows_native_icons(
                window,
                icon_path,
                native_api=native_api,
            )
            _retained_native_icon_handles.extend(handles)
        except (AttributeError, OSError):
            window.iconbitmap(bitmap=str(icon_path))
    else:
        try:
            window.iconbitmap(bitmap=str(icon_path))
        except tk.TclError:
            pass
