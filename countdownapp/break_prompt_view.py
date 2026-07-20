from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
from tkinter import ttk

from .presentation import runtime_window_layout, window_ui_scale


@dataclass(frozen=True)
class BreakPromptBindings:
    duration_var: tk.StringVar
    on_start: Callable[[], None]
    on_skip: Callable[[], None]
    on_shutdown: Callable[[], None]


class BreakPromptView:
    """Owns the long-break confirmation page and its responsive layout."""

    def __init__(self, root: tk.Tk, bindings: BreakPromptBindings) -> None:
        self._root = root
        self._bindings = bindings
        self.frame = ttk.Frame(root, padding=(30, 24), style="App.TFrame")
        self._build_content()

    @property
    def is_visible(self) -> bool:
        return bool(self.frame.winfo_manager())

    @property
    def required_height(self) -> int:
        return self.frame.winfo_reqheight()

    def show(self) -> None:
        self.frame.pack(fill="both", expand=True)
        self.apply_window_layout()

    def hide(self) -> None:
        self.frame.pack_forget()

    def apply_window_layout(self) -> None:
        self._root.update_idletasks()
        layout = runtime_window_layout(
            self._root.winfo_screenwidth(),
            self._root.winfo_screenheight(),
            controls_expanded=False,
            minimum_content_height=self.required_height,
            ui_scale=window_ui_scale(self._root),
        )
        self._root.minsize(layout.min_width, layout.min_height)
        self._root.geometry(layout.geometry)

    def _build_content(self) -> None:
        card = ttk.Frame(self.frame, padding=(24, 20), style="Form.TFrame")
        card.pack(fill="x", padx=30)

        ttk.Label(card, text="专注完成", style="Title.TLabel").pack(pady=(0, 8))
        ttk.Label(
            card,
            text="要开始大休息吗？休息期间不会产生随机提醒。",
            style="Phase.TLabel",
        ).pack(pady=(0, 16))

        duration_row = ttk.Frame(card, style="Form.TFrame")
        duration_row.pack()
        ttk.Label(duration_row, text="休息分钟数", style="Form.TLabel").pack(
            side="left"
        )
        ttk.Entry(
            duration_row,
            textvariable=self._bindings.duration_var,
            width=8,
        ).pack(side="left", padx=(10, 0))

        actions = ttk.Frame(card, style="Form.TFrame")
        actions.pack(fill="x", pady=(20, 0))
        for column in range(3):
            actions.columnconfigure(column, weight=1, uniform="break-action")
        ttk.Button(
            actions, text="开始休息", command=self._bindings.on_start
        ).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ttk.Button(actions, text="跳过", command=self._bindings.on_skip).grid(
            row=0, column=1, sticky="ew", padx=4
        )
        ttk.Button(
            actions, text="退出程序", command=self._bindings.on_shutdown
        ).grid(row=0, column=2, sticky="ew", padx=(4, 0))
