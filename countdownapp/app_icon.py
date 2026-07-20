from __future__ import annotations

import ctypes
import sys
import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from .resources import resource_path


APP_USER_MODEL_ID = "CountdownApp.FocusTimer"


class IconWindow(Protocol):
    def iconphoto(self, default: bool, image: object) -> None: ...
    def iconbitmap(self, *, bitmap: str) -> None: ...


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


def apply_window_icon(
    root: IconWindow,
    *,
    resolve_resource: Callable[[str], Path] = resource_path,
    image_factory: Callable[[str], object] = _load_png,
) -> object:
    """Apply one icon family to the root and all subsequently created windows."""
    photo = image_factory(str(resolve_resource("clock_icon.png")))
    root.iconphoto(True, photo)
    try:
        root.iconbitmap(bitmap=str(resolve_resource("clock_icon.ico")))
    except tk.TclError:
        # PNG remains the portable icon source on platforms without ICO support.
        pass
    return photo
