from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
from tkinter import ttk

from .presentation import responsive_window_layout, scroll_fraction_to_reveal
from .reminder_view import FLOW_FEEDBACK_LABEL
from .settings_form import (
    AMBIENT_TEXTURE_OPTIONS,
    AUDIO_OPTIONS,
    NOISE_OPTIONS,
    SOLFEGGIO_OPTIONS,
    SettingsForm,
)
from .startup import StartupMode


STARTUP_OPTIONS = {
    "关闭": StartupMode.OFF,
    "开机启动（显示主界面）": StartupMode.VISIBLE,
    "开机静默启动（仅显示托盘图标）": StartupMode.SILENT,
}

PAUSE_HOTKEY_PRESETS = (
    "Alt+Shift+P",
    "Ctrl+Alt+P",
    "Ctrl+Shift+P",
    "Alt+F9",
)

WINDOW_HOTKEY_PRESETS = (
    "Alt+Shift+O",
    "Ctrl+Alt+O",
    "Ctrl+Shift+O",
    "Alt+F10",
)


@dataclass(frozen=True)
class SettingsViewBindings:
    on_open_v2: Callable[[], None]
    on_test_audio: Callable[[bool], None]
    on_choose_audio: Callable[[bool], None]
    on_preview_ambient: Callable[[], None]
    on_stop_ambient: Callable[[], None]
    on_ambient_volume_change: Callable[[str], None]
    on_floating_status_change: Callable[[], None]
    on_global_hotkeys_change: Callable[[], None]
    on_close_to_tray_change: Callable[[], None]
    on_startup_change: Callable[[], None]
    on_start_focus: Callable[[], None]
    on_shutdown: Callable[[], None]


class SettingsView:
    """Owns the complete main settings page and its responsive behavior."""

    def __init__(
        self,
        root: tk.Tk,
        form: SettingsForm,
        bindings: SettingsViewBindings,
    ) -> None:
        self._root = root
        self._form = form
        self._bindings = bindings
        self._more_expanded = False
        self._startup_var = tk.StringVar(root)
        self._v2_summary_var = tk.StringVar(root)

        self.frame = ttk.Frame(root, padding=(26, 20), style="App.TFrame")
        self._build_header()
        self._build_scrollable_form()
        self._build_footer()
        self._root.bind_all("<MouseWheel>", self._on_mousewheel, add="+")

    @property
    def is_visible(self) -> bool:
        return bool(self.frame.winfo_manager())

    @property
    def more_expanded(self) -> bool:
        return self._more_expanded

    @property
    def startup_mode(self) -> StartupMode:
        return STARTUP_OPTIONS.get(self._startup_var.get(), StartupMode.OFF)

    def show(self) -> None:
        self.frame.pack(fill="both", expand=True)
        self.apply_window_layout()

    def hide(self) -> None:
        self.frame.pack_forget()

    def set_error(self, message: str) -> None:
        self._form_error.config(text=message)

    def set_startup_mode(self, mode: StartupMode) -> None:
        label = next(
            (label for label, value in STARTUP_OPTIONS.items() if value is mode),
            "关闭",
        )
        self._startup_var.set(label)

    def refresh_algorithm(self) -> None:
        if self._form.algorithm.get() == "V2":
            self._interval_min_entry.configure(textvariable=self._form.anchor_min)
            self._interval_max_entry.configure(textvariable=self._form.anchor_max)
            self._update_v2_summary()
            self._v2_summary_label.grid()
            self._v2_button.grid()
        else:
            self._interval_min_entry.configure(textvariable=self._form.classic_min)
            self._interval_max_entry.configure(textvariable=self._form.classic_max)
            self._v2_summary_label.grid_remove()
            self._v2_button.grid_remove()

    def refresh_hotkey_controls(self) -> None:
        state = "disabled" if self._form.global_hotkeys.get() else "normal"
        self._pause_hotkey_box.configure(state=state)
        self._window_hotkey_box.configure(state=state)

    def reset_v2_defaults(self) -> None:
        try:
            self._form.reset_v2_defaults()
        except ValueError as error:
            self.set_error(str(error))
            return
        self.refresh_algorithm()

    def apply_window_layout(self) -> None:
        layout = responsive_window_layout(
            self._root.winfo_screenwidth(), self._root.winfo_screenheight()
        )
        self._root.minsize(layout.min_width, layout.min_height)
        self._root.geometry(layout.geometry)

    def _build_header(self) -> None:
        ttk.Label(self.frame, text="CountdownApp V2", style="Title.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            self.frame,
            text="随机微休息 · 专注节律 · 本地运行",
            style="Subtitle.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(2, 12))
        self.frame.columnconfigure(0, weight=1)
        self.frame.rowconfigure(2, weight=1)

    def _build_scrollable_form(self) -> None:
        self._canvas = tk.Canvas(
            self.frame,
            background="#f4f7fb",
            borderwidth=0,
            highlightthickness=0,
        )
        scrollbar = ttk.Scrollbar(
            self.frame, orient="vertical", command=self._canvas.yview
        )
        self._canvas.configure(yscrollcommand=scrollbar.set)
        self._canvas.grid(row=2, column=0, sticky="nsew")
        scrollbar.grid(row=2, column=1, sticky="ns")

        self._content = ttk.Frame(
            self._canvas, padding=(12, 14), style="App.TFrame"
        )
        self._content.columnconfigure(0, weight=1)
        canvas_window = self._canvas.create_window(
            (0, 0), window=self._content, anchor="nw"
        )
        self._content.bind(
            "<Configure>",
            lambda _event: self._canvas.configure(
                scrollregion=self._canvas.bbox("all")
            ),
        )
        self._canvas.bind(
            "<Configure>",
            lambda event: self._canvas.itemconfigure(
                canvas_window, width=event.width
            ),
        )

        form = ttk.Frame(self._content, padding=(32, 14), style="Form.TFrame")
        form.grid(row=0, column=0, sticky="ew", padx=8)
        form.columnconfigure(1, weight=1)
        self._build_core_options(form)
        self._build_more_settings(form)

    def _build_core_options(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="随机算法", style="Form.TLabel").grid(
            row=0, column=0, sticky="e", pady=7
        )
        algorithm = ttk.Combobox(
            parent,
            textvariable=self._form.algorithm,
            values=("Classic", "V2"),
            state="readonly",
            width=22,
        )
        algorithm.grid(row=0, column=1, sticky="ew", padx=(12, 8), pady=7)
        algorithm.bind("<<ComboboxSelected>>", lambda _event: self.refresh_algorithm())
        self._entry_row(parent, 1, "专注时间", self._form.total, "分钟")

        presets = ttk.Frame(parent, style="Form.TFrame")
        presets.grid(row=2, column=1, sticky="w", padx=(12, 0), pady=(0, 5))
        for minutes in (30, 60, 90):
            ttk.Button(
                presets,
                text=str(minutes),
                width=4,
                command=lambda value=minutes: self._set_duration_preset(value),
            ).pack(side="left", padx=2)

        ttk.Label(parent, text="最小间隔", style="Form.TLabel").grid(
            row=3, column=0, sticky="e", pady=7
        )
        self._interval_min_entry = ttk.Entry(parent, width=22)
        self._interval_min_entry.grid(
            row=3, column=1, sticky="ew", padx=(12, 8), pady=7
        )
        ttk.Label(parent, text="分钟", style="Form.TLabel").grid(
            row=3, column=2, sticky="w"
        )
        ttk.Label(parent, text="最大间隔", style="Form.TLabel").grid(
            row=4, column=0, sticky="e", pady=7
        )
        self._interval_max_entry = ttk.Entry(parent, width=22)
        self._interval_max_entry.grid(
            row=4, column=1, sticky="ew", padx=(12, 8), pady=7
        )
        ttk.Label(parent, text="分钟", style="Form.TLabel").grid(
            row=4, column=2, sticky="w"
        )
        self._entry_row(parent, 5, "微休息时间", self._form.microbreak, "秒")
        ttk.Separator(parent).grid(
            row=6, column=0, columnspan=3, sticky="ew", pady=12
        )
        self._entry_row(parent, 7, "大休息时间", self._form.long_break, "分钟")
        ttk.Label(parent, text="休息倒计时", style="Form.TLabel").grid(
            row=8, column=0, sticky="e", pady=7
        )
        ttk.Checkbutton(
            parent,
            text="启用微休息倒计时和回归铃",
            variable=self._form.break_countdown,
            style="Form.TCheckbutton",
        ).grid(row=8, column=1, columnspan=2, sticky="w", padx=(12, 0), pady=7)
        ttk.Separator(parent).grid(
            row=9, column=0, columnspan=3, sticky="ew", pady=12
        )

        self._v2_summary_label = ttk.Label(
            parent,
            textvariable=self._v2_summary_var,
            style="FormHint.TLabel",
            wraplength=340,
            justify="left",
        )
        self._v2_summary_label.grid(
            row=10, column=0, columnspan=2, sticky="w", pady=5
        )
        self._settings_actions = ttk.Frame(parent, style="Form.TFrame")
        self._settings_actions.grid(row=10, column=2, sticky="e", pady=5)
        self._v2_button = ttk.Button(
            self._settings_actions,
            text="调整 V2",
            command=self._bindings.on_open_v2,
        )
        self._v2_button.grid(row=0, column=0, padx=(0, 6))
        for variable in (
            self._form.anchor_min,
            self._form.anchor_max,
            self._form.deep_min,
            self._form.deep_max,
            self._form.fatigue_min,
            self._form.fatigue_max,
        ):
            variable.trace_add("write", self._update_v2_summary)

    def _build_more_settings(self, parent: ttk.Frame) -> None:
        self._more_button = ttk.Button(
            self._settings_actions,
            text="更多设置 ▾",
            command=self._toggle_more_settings,
        )
        self._more_button.grid(row=0, column=1)
        self._more_frame = ttk.Frame(
            parent, padding=(0, 8, 0, 0), style="Form.TFrame"
        )
        self._more_frame.columnconfigure(0, weight=1)
        self._build_reminder_section()
        self._build_ambient_section()
        self._build_behavior_section()

    def _build_reminder_section(self) -> None:
        section = ttk.LabelFrame(
            self._more_frame,
            text="提醒与铃声",
            padding=12,
            style="Settings.TLabelframe",
        )
        section.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        section.columnconfigure(1, weight=1)
        ttk.Label(section, text="提醒强度", style="Form.TLabel").grid(
            row=0, column=0, sticky="e", pady=4
        )
        ttk.Combobox(
            section,
            textvariable=self._form.preset,
            values=("平衡", "强干预"),
            state="readonly",
            width=18,
        ).grid(row=0, column=1, columnspan=3, sticky="ew", padx=(12, 0), pady=4)
        ttk.Checkbutton(
            section,
            text=(
                "在提醒中显示反馈按钮：仍在任务 / 刚才走神 / "
                f"{FLOW_FEEDBACK_LABEL}"
            ),
            variable=self._form.adaptive,
            style="Form.TCheckbutton",
        ).grid(row=1, column=0, columnspan=4, sticky="w", pady=4)
        ttk.Label(
            section,
            text="根据反馈自动调整下一次提醒间隔",
            style="FormHint.TLabel",
        ).grid(row=2, column=0, columnspan=4, sticky="w", padx=(20, 0), pady=(0, 4))
        self._audio_row(section, 3, "微休息开始铃", self._form.audio, False)
        self._audio_row(section, 4, "回归专注铃", self._form.return_audio, True)

    def _audio_row(
        self,
        parent: ttk.LabelFrame,
        row: int,
        label: str,
        variable: tk.StringVar,
        is_return: bool,
    ) -> None:
        ttk.Label(parent, text=label, style="Form.TLabel").grid(
            row=row, column=0, sticky="e", pady=4
        )
        ttk.Combobox(
            parent,
            textvariable=variable,
            values=tuple(AUDIO_OPTIONS),
            state="readonly",
            width=18,
        ).grid(row=row, column=1, sticky="ew", padx=(12, 8), pady=4)
        ttk.Button(
            parent,
            text="试听",
            command=lambda: self._bindings.on_test_audio(is_return),
        ).grid(row=row, column=2, padx=4)
        ttk.Button(
            parent,
            text="选择文件",
            command=lambda: self._bindings.on_choose_audio(is_return),
        ).grid(row=row, column=3)

    def _build_ambient_section(self) -> None:
        section = ttk.LabelFrame(
            self._more_frame,
            text="持续背景音（可组合）",
            padding=12,
            style="Settings.TLabelframe",
        )
        section.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        section.columnconfigure(1, weight=1)
        ttk.Label(section, text="基础噪音", style="Form.TLabel").grid(
            row=0, column=0, sticky="e", pady=4
        )
        ttk.Combobox(
            section,
            textvariable=self._form.ambient,
            values=tuple(NOISE_OPTIONS),
            state="readonly",
            width=24,
        ).grid(row=0, column=1, sticky="ew", padx=(12, 8), pady=4)
        ttk.Button(
            section,
            text="试听组合",
            command=self._bindings.on_preview_ambient,
        ).grid(row=0, column=2, padx=4, pady=4)
        ttk.Button(
            section,
            text="停止",
            command=self._bindings.on_stop_ambient,
        ).grid(row=0, column=3, pady=4)
        ttk.Label(section, text="环境录音", style="Form.TLabel").grid(
            row=1, column=0, sticky="e", pady=4
        )
        ttk.Combobox(
            section,
            textvariable=self._form.ambient_texture,
            values=tuple(AMBIENT_TEXTURE_OPTIONS),
            state="readonly",
            width=24,
        ).grid(row=1, column=1, columnspan=3, sticky="ew", padx=(12, 0), pady=4)
        ttk.Label(section, text="Solfeggio 频率", style="Form.TLabel").grid(
            row=2, column=0, sticky="e", pady=4
        )
        ttk.Combobox(
            section,
            textvariable=self._form.solfeggio,
            values=tuple(SOLFEGGIO_OPTIONS),
            state="readonly",
            width=24,
        ).grid(row=2, column=1, columnspan=3, sticky="ew", padx=(12, 0), pady=4)
        ttk.Label(section, text="背景音量", style="Form.TLabel").grid(
            row=3, column=0, sticky="e", pady=4
        )
        ttk.Scale(
            section,
            from_=0,
            to=100,
            variable=self._form.ambient_volume,
            command=self._bindings.on_ambient_volume_change,
        ).grid(row=3, column=1, columnspan=2, sticky="ew", padx=(12, 8), pady=4)
        ttk.Label(
            section,
            textvariable=self._form.ambient_volume_label,
            style="FormHint.TLabel",
            width=5,
        ).grid(row=3, column=3, sticky="w")

    def _build_behavior_section(self) -> None:
        section = ttk.LabelFrame(
            self._more_frame,
            text="界面、快捷键与启动",
            padding=12,
            style="Settings.TLabelframe",
        )
        section.grid(row=2, column=0, sticky="ew")
        section.columnconfigure(1, weight=1)
        ttk.Checkbutton(
            section,
            text="显示下一次提醒的剩余时间（默认遮蔽，减少等待焦虑）",
            variable=self._form.show_next_reminder,
            style="Form.TCheckbutton",
        ).grid(row=0, column=0, columnspan=4, sticky="w", pady=4)
        ttk.Checkbutton(
            section,
            text="显示置顶悬浮计时条（右键或 × 可临时隐藏）",
            variable=self._form.floating_status,
            command=self._bindings.on_floating_status_change,
            style="Form.TCheckbutton",
        ).grid(row=1, column=0, columnspan=4, sticky="w", pady=4)
        ttk.Checkbutton(
            section,
            text="启用全局快捷键",
            variable=self._form.global_hotkeys,
            command=self._bindings.on_global_hotkeys_change,
            style="Form.TCheckbutton",
        ).grid(row=2, column=0, columnspan=4, sticky="w", pady=4)
        ttk.Label(section, text="暂停 / 继续", style="Form.TLabel").grid(
            row=3, column=0, sticky="e", pady=4
        )
        self._pause_hotkey_box = ttk.Combobox(
            section,
            textvariable=self._form.pause_hotkey,
            values=PAUSE_HOTKEY_PRESETS,
            width=24,
        )
        self._pause_hotkey_box.grid(
            row=3, column=1, columnspan=3, sticky="ew", padx=(12, 0), pady=4
        )
        ttk.Label(section, text="显示 / 隐藏", style="Form.TLabel").grid(
            row=4, column=0, sticky="e", pady=4
        )
        self._window_hotkey_box = ttk.Combobox(
            section,
            textvariable=self._form.window_hotkey,
            values=WINDOW_HOTKEY_PRESETS,
            width=24,
        )
        self._window_hotkey_box.grid(
            row=4, column=1, columnspan=3, sticky="ew", padx=(12, 0), pady=4
        )
        ttk.Checkbutton(
            section,
            text="关闭主窗口时隐藏到托盘（任务栏不显示）",
            variable=self._form.close_to_tray,
            command=self._bindings.on_close_to_tray_change,
            style="Form.TCheckbutton",
        ).grid(row=5, column=0, columnspan=4, sticky="w", pady=4)
        ttk.Label(section, text="开机启动", style="Form.TLabel").grid(
            row=6, column=0, sticky="e", pady=4
        )
        startup = ttk.Combobox(
            section,
            textvariable=self._startup_var,
            values=tuple(STARTUP_OPTIONS),
            state="readonly",
            width=30,
        )
        startup.grid(
            row=6, column=1, columnspan=3, sticky="ew", padx=(12, 0), pady=4
        )
        startup.bind(
            "<<ComboboxSelected>>",
            lambda _event: self._bindings.on_startup_change(),
        )

    def _build_footer(self) -> None:
        self._form_error = ttk.Label(
            self.frame,
            foreground="#b42318",
            background="#f4f7fb",
            wraplength=650,
        )
        self._form_error.grid(row=3, column=0, columnspan=2, pady=(8, 2))
        actions = ttk.Frame(self.frame, style="App.TFrame")
        actions.grid(row=4, column=0, columnspan=2, pady=(6, 0))
        ttk.Button(
            actions,
            text="开始专注",
            style="Primary.TButton",
            command=self._bindings.on_start_focus,
        ).pack(side="left", padx=6)
        ttk.Button(
            actions,
            text="退出程序",
            command=self._bindings.on_shutdown,
        ).pack(side="left", padx=6)

    @staticmethod
    def _entry_row(
        parent: tk.Misc,
        row: int,
        label: str,
        variable: tk.StringVar,
        unit: str,
    ) -> None:
        ttk.Label(parent, text=label, style="Form.TLabel").grid(
            row=row, column=0, sticky="e", pady=7
        )
        ttk.Entry(parent, textvariable=variable, width=22).grid(
            row=row, column=1, sticky="ew", padx=(12, 8), pady=7
        )
        ttk.Label(parent, text=unit, style="Form.TLabel").grid(
            row=row, column=2, sticky="w"
        )

    def _set_duration_preset(self, minutes: int) -> None:
        self._form.total.set(str(minutes))
        self._form.algorithm.set("V2" if minutes >= 60 else "Classic")
        self.reset_v2_defaults()

    def _update_v2_summary(self, *_args: object) -> None:
        if self._form.algorithm.get() != "V2":
            return
        self._v2_summary_var.set(
            "V2 节律：锚定 "
            f"{self._form.anchor_min.get()}–{self._form.anchor_max.get()} ｜ 深度 "
            f"{self._form.deep_min.get()}–{self._form.deep_max.get()} ｜ 疲劳 "
            f"{self._form.fatigue_min.get()}–{self._form.fatigue_max.get()} 分钟"
        )

    def _toggle_more_settings(self) -> None:
        self._more_expanded = not self._more_expanded
        if self._more_expanded:
            self._more_frame.grid(row=11, column=0, columnspan=3, sticky="ew")
            self._more_button.config(text="收起更多设置 ▴")
            self._root.after_idle(self._reveal_more_settings)
        else:
            self._more_frame.grid_remove()
            self._more_button.config(text="更多设置 ▾")

    def _reveal_more_settings(self) -> None:
        if not self._more_expanded or not self._canvas.winfo_exists():
            return
        self._root.update_idletasks()
        bounds = self._canvas.bbox("all")
        if bounds is None:
            return
        target_y = self._more_button.winfo_rooty() - self._content.winfo_rooty()
        content_height = bounds[3] - bounds[1]
        self._canvas.yview_moveto(
            scroll_fraction_to_reveal(target_y, content_height)
        )

    def _on_mousewheel(self, event: tk.Event) -> str | None:
        if not self._canvas.winfo_viewable() or event.delta == 0:
            return None
        pointer_x, pointer_y = self._root.winfo_pointerxy()
        left = self._canvas.winfo_rootx()
        top = self._canvas.winfo_rooty()
        if not (
            left <= pointer_x < left + self._canvas.winfo_width()
            and top <= pointer_y < top + self._canvas.winfo_height()
        ):
            return None
        direction = -1 if event.delta > 0 else 1
        self._canvas.yview_scroll(direction * 3, "units")
        return "break"
