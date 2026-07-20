from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from .resources import resource_path


class IconWindow(Protocol):
    def iconphoto(self, default: bool, image: object) -> None: ...
    def iconbitmap(self, *, default: str) -> None: ...


def _load_png(path: str) -> tk.PhotoImage:
    return tk.PhotoImage(file=path)


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
        root.iconbitmap(default=str(resolve_resource("clock_icon.ico")))
    except tk.TclError:
        # PNG remains the portable icon source on platforms without ICO support.
        pass
    return photo
