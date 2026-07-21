from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

from .presentation import v2_window_layout, window_ui_scale
from .settings_form import SettingsForm


class V2SettingsDialog:
    """Owns the V2 phase editor window and its complete lifecycle."""

    def __init__(
        self,
        root: tk.Tk,
        form: SettingsForm,
        on_reset: Callable[[], None],
        on_closed: Callable[[], None],
    ) -> None:
        self._root = root
        self._form = form
        self._on_reset = on_reset
        self._on_closed = on_closed
        self._window: tk.Toplevel | None = None

    @property
    def is_open(self) -> bool:
        if self._window is None:
            return False
        try:
            return bool(self._window.winfo_exists())
        except tk.TclError:
            self._window = None
            return False

    def show(self) -> None:
        if self.is_open:
            assert self._window is not None
            self._window.deiconify()
            self._window.lift()
            return

        window = tk.Toplevel(self._root)
        self._window = window
        window.title("V2 节律设置")
        layout = v2_window_layout(
            window.winfo_screenwidth(),
            window.winfo_screenheight(),
            ui_scale=window_ui_scale(window),
        )
        window.geometry(layout.geometry)
        window.minsize(layout.min_width, layout.min_height)
        window.transient(self._root)

        body = ttk.Frame(window, padding=(16, 12), style="App.TFrame")
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        ttk.Label(body, text="V2 节律设置", style="Section.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 2)
        )
        ttk.Label(
            body,
            text="主页面的最小/最大间隔对应注意力锚定期。这里可以调整全部阶段。",
            style="Subtitle.TLabel",
            wraplength=510,
        ).grid(row=1, column=0, sticky="w", pady=(0, 6))
        self._build_boundaries(body)
        self._build_intervals(body)

        actions = ttk.Frame(body, style="App.TFrame")
        actions.grid(row=4, column=0, sticky="e", pady=(8, 0))
        ttk.Button(
            actions,
            text="恢复默认节律",
            command=self._on_reset,
        ).pack(side="left", padx=(0, 8))
        ttk.Button(
            actions,
            text="完成",
            style="Primary.TButton",
            command=self.close,
        ).pack(side="left")
        window.update_idletasks()
        layout = v2_window_layout(
            window.winfo_screenwidth(),
            window.winfo_screenheight(),
            ui_scale=window_ui_scale(window),
            minimum_content_height=body.winfo_reqheight(),
        )
        window.geometry(layout.geometry)
        window.minsize(layout.min_width, layout.min_height)
        window.protocol("WM_DELETE_WINDOW", self.close)

    def close(self) -> None:
        window, self._window = self._window, None
        if window is None:
            return
        try:
            window.destroy()
        except tk.TclError:
            pass
        self._on_closed()

    def _build_boundaries(self, body: ttk.Frame) -> None:
        boundaries = ttk.LabelFrame(
            body,
            text="阶段边界",
            padding=(10, 4),
            style="Settings.TLabelframe",
        )
        boundaries.grid(row=2, column=0, sticky="ew", pady=(0, 6))
        boundaries.columnconfigure(1, weight=1)
        for row, (label, variable) in enumerate(
            (
                ("锚定期结束", self._form.anchor_end),
                ("疲劳期开始", self._form.fatigue_start),
            )
        ):
            ttk.Label(boundaries, text=label).grid(
                row=row, column=0, sticky="w", padx=(0, 12), pady=1
            )
            ttk.Entry(boundaries, textvariable=variable, width=12).grid(
                row=row, column=1, sticky="ew", pady=1
            )
            ttk.Label(boundaries, text="分钟").grid(
                row=row, column=2, sticky="w", padx=(8, 0), pady=1
            )

    def _build_intervals(self, body: ttk.Frame) -> None:
        intervals = ttk.LabelFrame(
            body,
            text="阶段随机间隔（分钟）",
            padding=(10, 4),
            style="Settings.TLabelframe",
        )
        intervals.grid(row=3, column=0, sticky="ew")
        intervals.columnconfigure((1, 2), weight=1)
        for column, text in enumerate(("阶段", "最小", "最大")):
            ttk.Label(intervals, text=text, style="Section.TLabel").grid(
                row=0,
                column=column,
                sticky="w",
                padx=(0, 12) if column == 0 else ((8, 0) if column == 2 else 0),
                pady=(0, 1),
            )
        rows = (
            ("锚定期", self._form.anchor_min, self._form.anchor_max),
            ("深度期", self._form.deep_min, self._form.deep_max),
            ("疲劳期", self._form.fatigue_min, self._form.fatigue_max),
        )
        for row, (label, minimum, maximum) in enumerate(rows, start=1):
            ttk.Label(intervals, text=label).grid(
                row=row, column=0, sticky="w", padx=(0, 12), pady=1
            )
            ttk.Entry(intervals, textvariable=minimum, width=10).grid(
                row=row, column=1, sticky="ew", pady=1
            )
            ttk.Entry(intervals, textvariable=maximum, width=10).grid(
                row=row, column=2, sticky="ew", padx=(8, 0), pady=1
            )
