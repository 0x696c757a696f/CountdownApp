from __future__ import annotations

import tkinter as tk
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from tkinter import ttk

from .presentation import RenderCache, runtime_window_layout, window_ui_scale


@dataclass(frozen=True)
class RuntimeBindings:
    noise_var: tk.StringVar
    texture_var: tk.StringVar
    tone_var: tk.StringVar
    volume_var: tk.DoubleVar
    volume_label_var: tk.StringVar
    on_ambient_change: Callable[[], None]
    on_volume_change: Callable[[str], None]
    on_volume_commit: Callable[[], None]
    on_stop_ambient: Callable[[], None]
    on_pause: Callable[[], None]
    on_stop_focus: Callable[[], None]
    on_hide: Callable[[], None]


@dataclass(frozen=True)
class RuntimeDisplay:
    timer: str
    phase: str
    interval: str
    feedback: str = ""


class RuntimeView:
    """Owns the running-session page and its responsive layout."""

    def __init__(
        self,
        root: tk.Tk,
        bindings: RuntimeBindings,
        noise_options: Sequence[str],
        texture_options: Sequence[str],
        tone_options: Sequence[str],
    ) -> None:
        self._root = root
        self._bindings = bindings
        self._cache = RenderCache()
        self._ambient_controls_expanded = False
        self._ambient_summary_var = tk.StringVar(value="已关闭")

        self.frame = ttk.Frame(root, padding=(24, 16), style="App.TFrame")
        self._build_dashboard()
        self._build_ambient_card(noise_options, texture_options, tone_options)
        self._build_actions()

    @property
    def is_visible(self) -> bool:
        return bool(self.frame.winfo_manager())

    @property
    def ambient_controls_expanded(self) -> bool:
        return self._ambient_controls_expanded

    @property
    def required_height(self) -> int:
        return self.frame.winfo_reqheight()

    def show_focus(self, ambient_summary: str) -> None:
        self._show_ambient_card()
        self.collapse_ambient_controls()
        self.set_ambient_summary(ambient_summary)
        self.set_pause_state(paused=False, long_break=False)
        self.frame.pack(fill="both", expand=True)
        self.apply_window_layout()

    def show_long_break(self) -> None:
        self.collapse_ambient_controls()
        self._ambient_card.pack_forget()
        self.set_pause_state(paused=False, long_break=True)
        self.frame.pack(fill="both", expand=True)
        self.apply_window_layout()

    def hide(self) -> None:
        self.frame.pack_forget()
        self.collapse_ambient_controls()

    def render(self, display: RuntimeDisplay) -> None:
        self._cache.update(
            "timer", display.timer, lambda value: self._timer_label.config(text=value)
        )
        self._cache.update(
            "phase", display.phase, lambda value: self._phase_label.config(text=value)
        )
        self._cache.update(
            "interval",
            display.interval,
            lambda value: self._interval_label.config(text=value),
        )
        self._cache.update(
            "feedback",
            display.feedback,
            lambda value: self._feedback_label.config(text=value),
        )

    def invalidate(self) -> None:
        self._cache.invalidate()

    def set_pause_state(self, paused: bool, long_break: bool = False) -> None:
        if long_break:
            text = "继续休息" if paused else "暂停休息"
        else:
            text = "继续专注" if paused else "暂停专注"
        self._pause_button.config(text=text)

    def set_ambient_summary(self, summary: str) -> None:
        self._ambient_summary_var.set(summary)

    def toggle_ambient_controls(self) -> None:
        if self._ambient_controls_expanded:
            self.collapse_ambient_controls()
        else:
            self._ambient_controls.pack(fill="x")
            self._ambient_stop_button.grid()
            self._ambient_toggle_button.config(text="收起")
            self._ambient_controls_expanded = True
        self.apply_window_layout()

    def collapse_ambient_controls(self) -> None:
        self._ambient_controls.pack_forget()
        self._ambient_stop_button.grid_remove()
        self._ambient_toggle_button.config(text="调整")
        self._ambient_controls_expanded = False

    def apply_window_layout(self) -> None:
        self._root.update_idletasks()
        layout = runtime_window_layout(
            self._root.winfo_screenwidth(),
            self._root.winfo_screenheight(),
            controls_expanded=self._ambient_controls_expanded,
            minimum_content_height=self.required_height,
            ui_scale=window_ui_scale(self._root),
        )
        self._root.minsize(layout.min_width, layout.min_height)
        self._root.geometry(layout.geometry)

    def _build_dashboard(self) -> None:
        dashboard = ttk.Frame(self.frame, padding=(16, 10), style="Form.TFrame")
        dashboard.pack(fill="x", padx=30)
        dashboard.columnconfigure(2, weight=1)
        timer_block = ttk.Frame(dashboard, style="Form.TFrame")
        timer_block.grid(row=0, column=0, sticky="nsew")
        ttk.Label(timer_block, text="剩余时间", style="FormHint.TLabel").pack(anchor="w")
        self._timer_label = ttk.Label(
            timer_block, text="00:00", style="DashboardTimer.TLabel"
        )
        self._timer_label.pack(anchor="w")
        ttk.Separator(dashboard, orient="vertical").grid(
            row=0, column=1, sticky="ns", padx=16
        )
        details = ttk.Frame(dashboard, style="Form.TFrame")
        details.grid(row=0, column=2, sticky="nsew")
        self._phase_label = ttk.Label(details, text="", style="Form.TLabel")
        self._phase_label.pack(anchor="w", pady=(2, 3))
        self._interval_label = ttk.Label(
            details,
            text="",
            style="FormHint.TLabel",
            wraplength=300,
            justify="left",
        )
        self._interval_label.pack(anchor="w", pady=2)
        self._feedback_label = ttk.Label(
            details,
            text="",
            style="FormHint.TLabel",
            wraplength=300,
            justify="left",
        )
        self._feedback_label.pack(anchor="w", pady=2)

    def _build_ambient_card(
        self,
        noise_options: Sequence[str],
        texture_options: Sequence[str],
        tone_options: Sequence[str],
    ) -> None:
        self._ambient_card = ttk.Frame(
            self.frame, padding=(16, 10), style="Form.TFrame"
        )
        self._ambient_card.pack(fill="x", padx=30, pady=(8, 0))
        bar = ttk.Frame(self._ambient_card, style="Form.TFrame")
        bar.pack(fill="x")
        bar.columnconfigure(1, weight=1)
        ttk.Label(bar, text="持续背景音", style="Form.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w"
        )
        ttk.Label(
            bar,
            textvariable=self._ambient_summary_var,
            style="FormHint.TLabel",
            wraplength=300,
            justify="left",
        ).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(2, 0))
        header_actions = ttk.Frame(bar, style="Form.TFrame")
        header_actions.grid(row=0, column=2, rowspan=2, sticky="e")
        self._ambient_stop_button = ttk.Button(
            header_actions,
            text="关闭",
            width=7,
            command=self._bindings.on_stop_ambient,
        )
        self._ambient_stop_button.grid(row=0, column=0, padx=(0, 6))
        self._ambient_stop_button.grid_remove()
        self._ambient_toggle_button = ttk.Button(
            header_actions,
            text="调整",
            width=7,
            command=self.toggle_ambient_controls,
        )
        self._ambient_toggle_button.grid(row=0, column=1)

        self._ambient_controls = ttk.Frame(
            self._ambient_card, padding=(0, 10, 0, 0), style="Form.TFrame"
        )
        self._ambient_controls.columnconfigure(1, weight=1)
        self._ambient_combobox_row(
            0, "基础噪音", self._bindings.noise_var, noise_options
        )
        self._ambient_combobox_row(
            1, "环境录音", self._bindings.texture_var, texture_options
        )
        self._ambient_combobox_row(
            2, "Solfeggio", self._bindings.tone_var, tone_options
        )
        ttk.Label(self._ambient_controls, text="音量", style="Form.TLabel").grid(
            row=3, column=0, sticky="e", pady=4
        )
        volume = ttk.Scale(
            self._ambient_controls,
            from_=0,
            to=100,
            variable=self._bindings.volume_var,
            command=self._bindings.on_volume_change,
        )
        volume.grid(row=3, column=1, sticky="ew", padx=(12, 8), pady=4)
        volume.bind("<ButtonRelease-1>", lambda _event: self._bindings.on_volume_commit())
        volume.bind("<KeyRelease>", lambda _event: self._bindings.on_volume_commit())
        ttk.Label(
            self._ambient_controls,
            textvariable=self._bindings.volume_label_var,
            style="FormHint.TLabel",
            width=5,
        ).grid(row=3, column=2, sticky="w")

    def _ambient_combobox_row(
        self,
        row: int,
        label: str,
        variable: tk.StringVar,
        options: Sequence[str],
    ) -> None:
        ttk.Label(self._ambient_controls, text=label, style="Form.TLabel").grid(
            row=row, column=0, sticky="e", pady=4
        )
        box = ttk.Combobox(
            self._ambient_controls,
            textvariable=variable,
            values=tuple(options),
            state="readonly",
        )
        box.grid(row=row, column=1, sticky="ew", padx=(12, 0), pady=4)
        box.bind("<<ComboboxSelected>>", lambda _event: self._bindings.on_ambient_change())

    def _build_actions(self) -> None:
        self._actions = ttk.Frame(self.frame)
        self._actions.pack(fill="x", padx=30, pady=12)
        for column in range(3):
            self._actions.columnconfigure(column, weight=1, uniform="runtime_actions")
        self._pause_button = ttk.Button(
            self._actions, text="暂停专注", command=self._bindings.on_pause
        )
        self._pause_button.grid(row=0, column=0, sticky="ew", padx=4)
        ttk.Button(
            self._actions, text="结束专注", command=self._bindings.on_stop_focus
        ).grid(row=0, column=1, sticky="ew", padx=4)
        ttk.Button(
            self._actions, text="隐藏到托盘", command=self._bindings.on_hide
        ).grid(row=0, column=2, sticky="ew", padx=4)

    def _show_ambient_card(self) -> None:
        if not self._ambient_card.winfo_manager():
            self._ambient_card.pack(
                fill="x", padx=30, pady=(8, 0), before=self._actions
            )
