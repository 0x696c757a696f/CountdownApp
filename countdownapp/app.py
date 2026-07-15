from __future__ import annotations

import math
import platform
import queue
import sys
import time
import tkinter as tk
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from secrets import SystemRandom
from types import TracebackType
from tkinter import filedialog, messagebox, ttk

from . import __version__
from .adaptive import AttentionFeedback
from .ambient_async import AsyncAmbientController
from .audio import AudioEngine, should_play_return_bell
from .config import AppSettings, ConfigStore
from .domain import (
    IntervalRange,
    ReminderPreset,
    SessionSettings,
    SessionState,
    V2Phase,
    reminder_coverage_warnings,
)
from .floating import FloatingStatusController, TkFloatingStatusView
from .hotkeys import GlobalHotkeyService
from .logging_config import configure_logging
from .presentation import (
    format_ambient_summary,
    format_feedback_summary,
    format_reminder_status,
    responsive_window_layout,
    runtime_window_layout,
    scroll_fraction_to_reveal,
    v2_window_layout,
)
from .resources import install_dir, resource_path
from .reminder_view import (
    FLOW_FEEDBACK_LABEL,
    ReminderResult,
    ReminderResultKind,
    ReminderView,
)
from .runtime_view import RuntimeBindings, RuntimeDisplay, RuntimeView
from .session import FocusSession, RuntimeEventKind
from .settings_form import (
    AUDIO_OPTIONS,
    NOISE_OPTIONS,
    SOLFEGGIO_OPTIONS,
    SettingsForm,
)
from .single_instance import SingleInstanceGuard, show_native_message
from .startup import StartupManager, StartupMode, should_start_hidden
from .tray import TrayService


PHASE_NAMES = {
    None: "Classic",
    V2Phase.ATTENTION_ANCHOR: "注意力锚定期",
    V2Phase.DEEP_FOCUS: "深度专注期",
    V2Phase.FATIGUE_SUPPORT: "疲劳维护期",
}

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


class CountdownApp:
    TICK_MS = 500
    TRAY_POLL_MS = 250

    def __init__(self, root: tk.Tk):
        self.root = root
        self.logger = configure_logging()
        self.logger.info(
            "Starting CountdownApp %s with Python %s on %s",
            __version__,
            platform.python_version(),
            platform.platform(),
        )
        self.store = ConfigStore()
        self.app_settings = self.store.migrate_legacy(
            [install_dir() / "settings.ini", Path.cwd() / "settings.ini"]
        )
        if self.store.last_save_error is not None:
            self.logger.warning(
                "Initial settings could not be saved: %s",
                self.store.last_save_error,
            )
        self.audio = AudioEngine(logger=self.logger)
        self.gui_callbacks: "queue.Queue[Callable[[], None]]" = queue.Queue()
        self.ambient_tasks = AsyncAmbientController(
            self.audio.play_prepared_ambient,
            self.gui_callbacks.put,
            logger=self.logger,
        )
        self.startup_manager = StartupManager()
        try:
            self.startup_mode = self.startup_manager.reconcile_mode()
        except OSError as error:
            self.logger.warning("Reading Windows startup setting failed: %s", error)
            self.startup_mode = StartupMode.OFF
        self.session: FocusSession | None = None
        self.session_generation = 0
        self.tick_after_id: str | None = None
        self.tray_after_id: str | None = None
        self.audio_after_id: str | None = None
        self.reminder_view = ReminderView(self.root)
        self.tray_commands: "queue.Queue[str]" = queue.Queue()
        self.tray = TrayService(resource_path("clock_icon.ico"), self.tray_commands, self.logger)
        self.hotkeys = GlobalHotkeyService(self.tray_commands, self.logger)
        self.floating_status = FloatingStatusController(self._create_floating_status_view)

        self._configure_root()
        self._build_ui()
        self._load_form(self.app_settings)
        self.floating_status.set_enabled(self.app_settings.floating_status_enabled)
        hotkey_start_failed = bool(
            self.app_settings.global_hotkeys_enabled
            and not self.hotkeys.start(
                self.app_settings.pause_hotkey,
                self.app_settings.window_hotkey,
            )
        )
        if hotkey_start_failed:
            self.global_hotkeys_var.set(False)
            self._refresh_hotkey_controls()
            self.app_settings = replace(self.app_settings, global_hotkeys_enabled=False)
            try:
                self.store.save(self.app_settings)
            except (OSError, ValueError) as error:
                self.logger.warning("Saving disabled hotkey preference failed: %s", error)
        tray_ready = self.tray.start()
        start_hidden = should_start_hidden(sys.argv, tray_ready=tray_ready)
        if start_hidden:
            self.root.withdraw()
        if self.store.last_recovery_path is not None:
            self.logger.warning(
                "Invalid settings preserved as %s",
                self.store.last_recovery_path.name,
            )
            if not start_hidden:
                backup_name = self.store.last_recovery_path.name
                self.root.after(
                    0,
                    lambda: messagebox.showwarning(
                        "配置已恢复",
                        f"原配置无法读取，已保留为 {backup_name}，本次使用默认设置。",
                    ),
                )
        if self.store.last_save_error is not None:
            warning = (
                "安装目录不可写，本次将使用内存默认设置；关闭程序后更改不会保留。"
            )
            if start_hidden:
                self.tray.notify("CountdownApp 配置未保存", warning)
            else:
                self.root.after(
                    0,
                    lambda: messagebox.showwarning("配置无法保存", warning),
                )
        if hotkey_start_failed and not start_hidden:
            self.root.after(
                0,
                lambda: messagebox.showwarning(
                    "全局快捷键不可用",
                    f"{self.hotkeys.last_error}\n\n功能已自动关闭。",
                ),
            )
        self.tray_after_id = self.root.after(self.TRAY_POLL_MS, self._poll_tray)
        self.logger.info("Application started")

    def _configure_root(self) -> None:
        self.root.title("CountdownApp V2")
        window_layout = responsive_window_layout(
            self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        )
        self.root.geometry(window_layout.geometry)
        self.root.minsize(window_layout.min_width, window_layout.min_height)
        self.root.configure(bg="#f4f7fb")
        self.root.protocol("WM_DELETE_WINDOW", self._on_window_close)
        style = ttk.Style(self.root)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        background = "#f4f7fb"
        card = "#ffffff"
        text = "#172033"
        muted = "#64748b"
        accent = "#4169e1"
        style.configure("App.TFrame", background=background)
        style.configure("Form.TFrame", background=card)
        style.configure(
            "Form.TLabel",
            background=card,
            foreground=text,
            font=("Microsoft YaHei UI", 11, "bold"),
        )
        style.configure(
            "FormHint.TLabel",
            background=card,
            foreground=muted,
            font=("Microsoft YaHei UI", 9),
        )
        style.configure(
            "Form.TCheckbutton",
            background=card,
            foreground=text,
            font=("Microsoft YaHei UI", 10),
        )
        style.configure(
            "Settings.TLabelframe",
            background=card,
            bordercolor="#dbe3ef",
            borderwidth=1,
            relief="solid",
        )
        style.configure(
            "Settings.TLabelframe.Label",
            background=card,
            foreground=text,
            font=("Microsoft YaHei UI", 10, "bold"),
        )
        style.configure(
            "Title.TLabel", background=background, foreground=text,
            font=("Microsoft YaHei UI", 22, "bold")
        )
        style.configure(
            "Subtitle.TLabel", background=background, foreground=muted,
            font=("Microsoft YaHei UI", 10)
        )
        style.configure(
            "DashboardTimer.TLabel", background=card, foreground=text,
            font=("Microsoft YaHei UI", 36, "bold")
        )
        style.configure(
            "Phase.TLabel", background=background, foreground=muted,
            font=("Microsoft YaHei UI", 13)
        )
        style.configure("TButton", font=("Microsoft YaHei UI", 10), padding=(10, 7))
        style.configure("Primary.TButton", font=("Microsoft YaHei UI", 11, "bold"), padding=(18, 9))
        style.map(
            "Primary.TButton",
            background=[("active", "#3157ce"), ("!disabled", accent)],
            foreground=[("!disabled", "#ffffff")],
        )
        style.configure(
            "TLabel", background=background, foreground=text,
            font=("Microsoft YaHei UI", 10)
        )
        style.configure("TEntry", font=("Microsoft YaHei UI", 10), padding=5)
        style.configure("TCombobox", font=("Microsoft YaHei UI", 10), padding=4)

    def _apply_settings_window_layout(self) -> None:
        window_layout = responsive_window_layout(
            self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        )
        self.root.minsize(window_layout.min_width, window_layout.min_height)
        self.root.geometry(window_layout.geometry)

    def _build_ui(self) -> None:
        self.settings_frame = ttk.Frame(self.root, padding=(26, 20), style="App.TFrame")
        self.break_prompt_frame = ttk.Frame(self.root, padding=30, style="App.TFrame")
        self.settings_frame.pack(fill="both", expand=True)

        ttk.Label(self.settings_frame, text="CountdownApp V2", style="Title.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            self.settings_frame,
            text="随机微休息 · 专注节律 · 本地运行",
            style="Subtitle.TLabel",
        ).grid(
            row=1, column=0, sticky="w", pady=(2, 12)
        )
        self.settings_frame.columnconfigure(0, weight=1)
        self.settings_frame.rowconfigure(2, weight=1)

        self.settings_form = SettingsForm(self.root)
        self.total_var = self.settings_form.total
        self.algorithm_var = self.settings_form.algorithm
        self.classic_min_var = self.settings_form.classic_min
        self.classic_max_var = self.settings_form.classic_max
        self.anchor_end_var = self.settings_form.anchor_end
        self.fatigue_start_var = self.settings_form.fatigue_start
        self.anchor_min_var = self.settings_form.anchor_min
        self.anchor_max_var = self.settings_form.anchor_max
        self.deep_min_var = self.settings_form.deep_min
        self.deep_max_var = self.settings_form.deep_max
        self.fatigue_min_var = self.settings_form.fatigue_min
        self.fatigue_max_var = self.settings_form.fatigue_max
        self.preset_var = self.settings_form.preset
        self.microbreak_var = self.settings_form.microbreak
        self.break_countdown_var = self.settings_form.break_countdown
        self.adaptive_var = self.settings_form.adaptive
        self.long_break_var = self.settings_form.long_break
        self.audio_var = self.settings_form.audio
        self.return_audio_var = self.settings_form.return_audio
        self.ambient_var = self.settings_form.ambient
        self.solfeggio_var = self.settings_form.solfeggio
        self.ambient_volume_var = self.settings_form.ambient_volume
        self.ambient_volume_label_var = self.settings_form.ambient_volume_label
        self.close_to_tray_var = self.settings_form.close_to_tray
        self.show_next_reminder_var = self.settings_form.show_next_reminder
        self.global_hotkeys_var = self.settings_form.global_hotkeys
        self.floating_status_var = self.settings_form.floating_status
        self.pause_hotkey_var = self.settings_form.pause_hotkey
        self.window_hotkey_var = self.settings_form.window_hotkey
        self.startup_var = tk.StringVar()

        self.basic_canvas = tk.Canvas(
            self.settings_frame,
            background="#f4f7fb",
            borderwidth=0,
            highlightthickness=0,
        )
        basic_scrollbar = ttk.Scrollbar(
            self.settings_frame, orient="vertical", command=self.basic_canvas.yview
        )
        self.basic_canvas.configure(yscrollcommand=basic_scrollbar.set)
        self.basic_canvas.grid(row=2, column=0, sticky="nsew")
        basic_scrollbar.grid(row=2, column=1, sticky="ns")

        basic_content = ttk.Frame(
            self.basic_canvas, padding=(12, 14), style="App.TFrame"
        )
        self.basic_content = basic_content
        basic_content.columnconfigure(0, weight=1)
        basic_window = self.basic_canvas.create_window(
            (0, 0), window=basic_content, anchor="nw"
        )
        basic_content.bind(
            "<Configure>",
            lambda _event: self.basic_canvas.configure(
                scrollregion=self.basic_canvas.bbox("all")
            ),
        )
        self.basic_canvas.bind(
            "<Configure>",
            lambda event: self.basic_canvas.itemconfigure(basic_window, width=event.width),
        )
        self.root.bind_all("<MouseWheel>", self._on_settings_mousewheel, add="+")

        form = ttk.Frame(basic_content, padding=(32, 14), style="Form.TFrame")
        form.grid(row=0, column=0, sticky="ew", padx=8)
        form.columnconfigure(1, weight=1)

        ttk.Label(form, text="随机算法", style="Form.TLabel").grid(
            row=0, column=0, sticky="e", pady=7
        )
        algorithm = ttk.Combobox(
            form,
            textvariable=self.algorithm_var,
            values=("Classic", "V2"),
            state="readonly",
            width=22,
        )
        algorithm.grid(row=0, column=1, sticky="ew", padx=(12, 8), pady=7)
        algorithm.bind(
            "<<ComboboxSelected>>", lambda _event: self._refresh_algorithm_controls()
        )

        self._setting_entry_row(form, 1, "专注时间", self.total_var, "分钟")
        preset_box = ttk.Frame(form, style="Form.TFrame")
        preset_box.grid(row=2, column=1, sticky="w", padx=(12, 0), pady=(0, 5))
        for minutes in (30, 60, 90):
            ttk.Button(
                preset_box,
                text=str(minutes),
                width=4,
                command=lambda value=minutes: self._set_duration_preset(value),
            ).pack(side="left", padx=2)

        self.interval_min_label = ttk.Label(form, text="最小间隔", style="Form.TLabel")
        self.interval_min_label.grid(row=3, column=0, sticky="e", pady=7)
        self.interval_min_entry = ttk.Entry(form, width=22)
        self.interval_min_entry.grid(row=3, column=1, sticky="ew", padx=(12, 8), pady=7)
        ttk.Label(form, text="分钟", style="Form.TLabel").grid(row=3, column=2, sticky="w")

        self.interval_max_label = ttk.Label(form, text="最大间隔", style="Form.TLabel")
        self.interval_max_label.grid(row=4, column=0, sticky="e", pady=7)
        self.interval_max_entry = ttk.Entry(form, width=22)
        self.interval_max_entry.grid(row=4, column=1, sticky="ew", padx=(12, 8), pady=7)
        ttk.Label(form, text="分钟", style="Form.TLabel").grid(row=4, column=2, sticky="w")

        self._setting_entry_row(form, 5, "微休息时间", self.microbreak_var, "秒")
        ttk.Separator(form).grid(row=6, column=0, columnspan=3, sticky="ew", pady=12)
        self._setting_entry_row(form, 7, "大休息时间", self.long_break_var, "分钟")

        ttk.Label(form, text="休息倒计时", style="Form.TLabel").grid(
            row=8, column=0, sticky="e", pady=7
        )
        ttk.Checkbutton(
            form,
            text="启用微休息倒计时和回归铃",
            variable=self.break_countdown_var,
            style="Form.TCheckbutton",
        ).grid(row=8, column=1, columnspan=2, sticky="w", padx=(12, 0), pady=7)

        ttk.Separator(form).grid(row=9, column=0, columnspan=3, sticky="ew", pady=12)
        self.v2_summary_var = tk.StringVar()
        self.v2_summary_label = ttk.Label(
            form,
            textvariable=self.v2_summary_var,
            style="FormHint.TLabel",
            wraplength=340,
            justify="left",
        )
        self.v2_summary_label.grid(row=10, column=0, columnspan=2, sticky="w", pady=5)
        settings_actions = ttk.Frame(form, style="Form.TFrame")
        settings_actions.grid(row=10, column=2, sticky="e", pady=5)
        self.v2_settings_button = ttk.Button(
            settings_actions, text="调整 V2", command=self._open_v2_settings
        )
        self.v2_settings_button.grid(row=0, column=0, padx=(0, 6))
        for variable in (
            self.anchor_min_var,
            self.anchor_max_var,
            self.deep_min_var,
            self.deep_max_var,
            self.fatigue_min_var,
            self.fatigue_max_var,
        ):
            variable.trace_add("write", self._update_v2_summary)

        self.more_visible = False
        self.more_button = ttk.Button(
            settings_actions, text="更多设置 ▾", command=self._toggle_more_settings
        )
        self.more_button.grid(row=0, column=1)
        self.more_frame = ttk.Frame(form, padding=(0, 8, 0, 0), style="Form.TFrame")
        self.more_frame.columnconfigure(0, weight=1)

        reminder_section = ttk.LabelFrame(
            self.more_frame,
            text="提醒与铃声",
            padding=12,
            style="Settings.TLabelframe",
        )
        reminder_section.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        reminder_section.columnconfigure(1, weight=1)

        ttk.Label(reminder_section, text="提醒强度", style="Form.TLabel").grid(
            row=0, column=0, sticky="e", pady=4
        )
        ttk.Combobox(
            reminder_section,
            textvariable=self.preset_var,
            values=("平衡", "强干预"),
            state="readonly",
            width=18,
        ).grid(row=0, column=1, columnspan=3, sticky="ew", padx=(12, 0), pady=4)
        ttk.Checkbutton(
            reminder_section,
            text=(
                "在提醒中显示反馈按钮：仍在任务 / 刚才走神 / "
                f"{FLOW_FEEDBACK_LABEL}"
            ),
            variable=self.adaptive_var,
            style="Form.TCheckbutton",
        ).grid(row=1, column=0, columnspan=4, sticky="w", pady=4)
        ttk.Label(
            reminder_section,
            text="根据反馈自动调整下一次提醒间隔",
            style="FormHint.TLabel",
        ).grid(row=2, column=0, columnspan=4, sticky="w", padx=(20, 0), pady=(0, 4))

        ttk.Label(reminder_section, text="微休息开始铃", style="Form.TLabel").grid(
            row=3, column=0, sticky="e", pady=4
        )
        ttk.Combobox(
            reminder_section,
            textvariable=self.audio_var,
            values=tuple(AUDIO_OPTIONS),
            state="readonly",
            width=18,
        ).grid(row=3, column=1, sticky="ew", padx=(12, 8), pady=4)
        ttk.Button(
            reminder_section, text="试听", command=lambda: self._test_audio(False)
        ).grid(row=3, column=2, padx=4)
        ttk.Button(
            reminder_section, text="选择文件", command=lambda: self._choose_audio(False)
        ).grid(row=3, column=3)

        ttk.Label(reminder_section, text="回归专注铃", style="Form.TLabel").grid(
            row=4, column=0, sticky="e", pady=4
        )
        ttk.Combobox(
            reminder_section,
            textvariable=self.return_audio_var,
            values=tuple(AUDIO_OPTIONS),
            state="readonly",
            width=18,
        ).grid(row=4, column=1, sticky="ew", padx=(12, 8), pady=4)
        ttk.Button(
            reminder_section, text="试听", command=lambda: self._test_audio(True)
        ).grid(row=4, column=2, padx=4)
        ttk.Button(
            reminder_section, text="选择文件", command=lambda: self._choose_audio(True)
        ).grid(row=4, column=3)

        ambient_section = ttk.LabelFrame(
            self.more_frame,
            text="持续背景音（可组合）",
            padding=12,
            style="Settings.TLabelframe",
        )
        ambient_section.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        ambient_section.columnconfigure(1, weight=1)

        ttk.Label(ambient_section, text="噪音底色", style="Form.TLabel").grid(
            row=0, column=0, sticky="e", pady=4
        )
        ttk.Combobox(
            ambient_section,
            textvariable=self.ambient_var,
            values=tuple(NOISE_OPTIONS),
            state="readonly",
            width=24,
        ).grid(row=0, column=1, sticky="ew", padx=(12, 8), pady=4)
        ttk.Button(
            ambient_section, text="试听组合", command=self._preview_ambient
        ).grid(row=0, column=2, padx=4, pady=4)
        ttk.Button(
            ambient_section, text="停止", command=self._stop_ambient_playback
        ).grid(row=0, column=3, pady=4)

        ttk.Label(ambient_section, text="Solfeggio 频率", style="Form.TLabel").grid(
            row=1, column=0, sticky="e", pady=4
        )
        ttk.Combobox(
            ambient_section,
            textvariable=self.solfeggio_var,
            values=tuple(SOLFEGGIO_OPTIONS),
            state="readonly",
            width=24,
        ).grid(row=1, column=1, columnspan=3, sticky="ew", padx=(12, 0), pady=4)

        ttk.Label(ambient_section, text="背景音量", style="Form.TLabel").grid(
            row=2, column=0, sticky="e", pady=4
        )
        ttk.Scale(
            ambient_section,
            from_=0,
            to=100,
            variable=self.ambient_volume_var,
            command=self._on_ambient_volume_changed,
        ).grid(row=2, column=1, columnspan=2, sticky="ew", padx=(12, 8), pady=4)
        ttk.Label(
            ambient_section,
            textvariable=self.ambient_volume_label_var,
            style="FormHint.TLabel",
            width=5,
        ).grid(row=2, column=3, sticky="w")

        behavior_section = ttk.LabelFrame(
            self.more_frame,
            text="界面、快捷键与启动",
            padding=12,
            style="Settings.TLabelframe",
        )
        behavior_section.grid(row=2, column=0, sticky="ew")
        behavior_section.columnconfigure(1, weight=1)

        ttk.Checkbutton(
            behavior_section,
            text="显示下一次提醒的剩余时间（默认遮蔽，减少等待焦虑）",
            variable=self.show_next_reminder_var,
            style="Form.TCheckbutton",
        ).grid(row=0, column=0, columnspan=4, sticky="w", pady=4)
        ttk.Checkbutton(
            behavior_section,
            text="显示置顶悬浮计时条（右键或 × 可临时隐藏）",
            variable=self.floating_status_var,
            command=self._on_floating_status_changed,
            style="Form.TCheckbutton",
        ).grid(row=1, column=0, columnspan=4, sticky="w", pady=4)
        ttk.Checkbutton(
            behavior_section,
            text="启用全局快捷键",
            variable=self.global_hotkeys_var,
            command=self._on_global_hotkeys_changed,
            style="Form.TCheckbutton",
        ).grid(row=2, column=0, columnspan=4, sticky="w", pady=4)
        ttk.Label(behavior_section, text="暂停 / 继续", style="Form.TLabel").grid(
            row=3, column=0, sticky="e", pady=4
        )
        self.pause_hotkey_box = ttk.Combobox(
            behavior_section,
            textvariable=self.pause_hotkey_var,
            values=PAUSE_HOTKEY_PRESETS,
            width=24,
        )
        self.pause_hotkey_box.grid(
            row=3, column=1, columnspan=3, sticky="ew", padx=(12, 0), pady=4
        )
        ttk.Label(behavior_section, text="显示 / 隐藏", style="Form.TLabel").grid(
            row=4, column=0, sticky="e", pady=4
        )
        self.window_hotkey_box = ttk.Combobox(
            behavior_section,
            textvariable=self.window_hotkey_var,
            values=WINDOW_HOTKEY_PRESETS,
            width=24,
        )
        self.window_hotkey_box.grid(
            row=4, column=1, columnspan=3, sticky="ew", padx=(12, 0), pady=4
        )
        ttk.Checkbutton(
            behavior_section,
            text="关闭主窗口时隐藏到托盘（任务栏不显示）",
            variable=self.close_to_tray_var,
            command=self._on_close_to_tray_changed,
            style="Form.TCheckbutton",
        ).grid(row=5, column=0, columnspan=4, sticky="w", pady=4)
        ttk.Label(
            behavior_section,
            text="开机启动",
            style="Form.TLabel",
        ).grid(row=6, column=0, sticky="e", pady=4)
        startup_box = ttk.Combobox(
            behavior_section,
            textvariable=self.startup_var,
            values=tuple(STARTUP_OPTIONS),
            state="readonly",
            width=30,
        )
        startup_box.grid(row=6, column=1, columnspan=3, sticky="ew", padx=(12, 0), pady=4)
        startup_box.bind("<<ComboboxSelected>>", lambda _event: self._on_startup_changed())

        self.form_error = ttk.Label(
            self.settings_frame, foreground="#b42318", background="#f4f7fb", wraplength=650
        )
        self.form_error.grid(row=3, column=0, columnspan=2, pady=(8, 2))
        actions = ttk.Frame(self.settings_frame, style="App.TFrame")
        actions.grid(row=4, column=0, columnspan=2, pady=(6, 0))
        ttk.Button(
            actions, text="开始专注", style="Primary.TButton", command=self._start_focus
        ).pack(side="left", padx=6)
        ttk.Button(actions, text="退出程序", command=self._shutdown).pack(side="left", padx=6)

        self.runtime_view = RuntimeView(
            self.root,
            RuntimeBindings(
                noise_var=self.ambient_var,
                tone_var=self.solfeggio_var,
                volume_var=self.ambient_volume_var,
                volume_label_var=self.ambient_volume_label_var,
                on_ambient_change=self._apply_runtime_ambient,
                on_volume_change=self._on_runtime_ambient_volume_changed,
                on_volume_commit=self._save_runtime_ambient_preferences,
                on_stop_ambient=self._stop_runtime_ambient,
                on_pause=self._toggle_pause,
                on_stop_focus=self._stop_focus,
                on_hide=self._minimize_to_tray,
            ),
            noise_options=tuple(NOISE_OPTIONS),
            tone_options=tuple(SOLFEGGIO_OPTIONS),
        )

        ttk.Label(self.break_prompt_frame, text="专注完成", style="Title.TLabel").pack(pady=30)
        ttk.Label(
            self.break_prompt_frame,
            text="要开始大休息吗？休息期间不会产生随机提醒。",
            style="Phase.TLabel",
        ).pack(pady=12)
        break_line = ttk.Frame(self.break_prompt_frame)
        break_line.pack(pady=10)
        ttk.Label(break_line, text="休息分钟数").pack(side="left")
        ttk.Entry(break_line, textvariable=self.long_break_var, width=8).pack(side="left", padx=8)
        break_actions = ttk.Frame(self.break_prompt_frame)
        break_actions.pack(pady=20)
        ttk.Button(break_actions, text="开始休息", command=self._start_long_break).pack(
            side="left", padx=5
        )
        ttk.Button(break_actions, text="跳过", command=self._skip_long_break).pack(
            side="left", padx=5
        )
        ttk.Button(break_actions, text="退出程序", command=self._shutdown).pack(
            side="left", padx=5
        )

    @staticmethod
    def _setting_entry_row(
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

    def _on_settings_mousewheel(self, event: tk.Event) -> str | None:
        if not self.basic_canvas.winfo_viewable() or event.delta == 0:
            return None
        pointer_x, pointer_y = self.root.winfo_pointerxy()
        left = self.basic_canvas.winfo_rootx()
        top = self.basic_canvas.winfo_rooty()
        if not (
            left <= pointer_x < left + self.basic_canvas.winfo_width()
            and top <= pointer_y < top + self.basic_canvas.winfo_height()
        ):
            return None
        direction = -1 if event.delta > 0 else 1
        self.basic_canvas.yview_scroll(direction * 3, "units")
        return "break"

    def _load_form(self, settings: AppSettings) -> None:
        self.settings_form.load(settings)
        self._refresh_hotkey_controls()
        self.startup_var.set(
            next(
                label
                for label, mode in STARTUP_OPTIONS.items()
                if mode is self.startup_mode
            )
        )
        self._refresh_algorithm_controls()
        self._refresh_runtime_ambient_summary()

    def _set_duration_preset(self, minutes: int) -> None:
        self.total_var.set(str(minutes))
        self.algorithm_var.set("V2" if minutes >= 60 else "Classic")
        self._reset_v2_defaults()

    def _reset_v2_defaults(self) -> None:
        try:
            self.settings_form.reset_v2_defaults()
        except ValueError as error:
            self.form_error.config(text=str(error))
            return
        if hasattr(self, "v2_summary_var"):
            self._refresh_algorithm_controls()

    def _refresh_algorithm_controls(self) -> None:
        if self.algorithm_var.get() == "V2":
            self.interval_min_entry.configure(textvariable=self.anchor_min_var)
            self.interval_max_entry.configure(textvariable=self.anchor_max_var)
            self._update_v2_summary()
            self.v2_summary_label.grid()
            self.v2_settings_button.grid()
        else:
            self.interval_min_entry.configure(textvariable=self.classic_min_var)
            self.interval_max_entry.configure(textvariable=self.classic_max_var)
            self.v2_summary_label.grid_remove()
            self.v2_settings_button.grid_remove()

    def _update_v2_summary(self, *_args: object) -> None:
        if not hasattr(self, "v2_summary_var") or self.algorithm_var.get() != "V2":
            return
        self.v2_summary_var.set(
            "V2 节律：锚定 "
            f"{self.anchor_min_var.get()}–{self.anchor_max_var.get()} ｜ 深度 "
            f"{self.deep_min_var.get()}–{self.deep_max_var.get()} ｜ 疲劳 "
            f"{self.fatigue_min_var.get()}–{self.fatigue_max_var.get()} 分钟"
        )

    def _toggle_more_settings(self) -> None:
        self.more_visible = not self.more_visible
        if self.more_visible:
            self.more_frame.grid(row=11, column=0, columnspan=3, sticky="ew")
            self.more_button.config(text="收起更多设置 ▴")
            self.root.after_idle(self._reveal_more_settings)
        else:
            self.more_frame.grid_remove()
            self.more_button.config(text="更多设置 ▾")

    def _reveal_more_settings(self) -> None:
        if not self.more_visible or not self.basic_canvas.winfo_exists():
            return
        self.root.update_idletasks()
        bounds = self.basic_canvas.bbox("all")
        if bounds is None:
            return
        # Keep the collapse action in view so expanding the section never
        # strands the user below a partially clipped button row.
        target_y = self.more_button.winfo_rooty() - self.basic_content.winfo_rooty()
        content_height = bounds[3] - bounds[1]
        self.basic_canvas.yview_moveto(
            scroll_fraction_to_reveal(target_y, content_height)
        )

    def _on_close_to_tray_changed(self) -> None:
        updated = replace(
            self.app_settings,
            close_to_tray=self.close_to_tray_var.get(),
        )
        try:
            self.store.save(updated)
            self.app_settings = updated
        except (OSError, ValueError) as error:
            self.logger.error("Saving close-to-tray preference failed: %s", error)
            messagebox.showwarning(
                "设置未保存",
                "本次关闭行为已经生效，但无法写入安装目录中的 settings.json。",
            )

    def _create_floating_status_view(
        self, on_hide: Callable[[], None]
    ) -> TkFloatingStatusView:
        initial_position = None
        if (
            self.app_settings.floating_x is not None
            and self.app_settings.floating_y is not None
        ):
            initial_position = (
                self.app_settings.floating_x,
                self.app_settings.floating_y,
            )
        return TkFloatingStatusView(
            self.root,
            on_hide,
            initial_position=initial_position,
            on_position_changed=self._on_floating_position_changed,
        )

    def _on_floating_position_changed(self, x: int, y: int) -> None:
        if self.app_settings.floating_x == x and self.app_settings.floating_y == y:
            return
        updated = replace(self.app_settings, floating_x=x, floating_y=y)
        try:
            self.store.save(updated)
            self.app_settings = updated
        except (OSError, ValueError) as error:
            self.logger.warning("Saving floating window position failed: %s", error)

    def _refresh_hotkey_controls(self) -> None:
        state = "disabled" if self.global_hotkeys_var.get() else "normal"
        self.pause_hotkey_box.configure(state=state)
        self.window_hotkey_box.configure(state=state)

    def _on_global_hotkeys_changed(self) -> None:
        enabled = self.global_hotkeys_var.get()
        if enabled and not self.hotkeys.start(
            self.pause_hotkey_var.get(), self.window_hotkey_var.get()
        ):
            self.global_hotkeys_var.set(False)
            enabled = False
            messagebox.showwarning(
                "全局快捷键不可用",
                f"{self.hotkeys.last_error}\n\n"
                "支持 Ctrl/Alt/Shift/Win 加 A–Z、0–9、F1–F12 或 Space。",
            )
        elif not enabled:
            self.hotkeys.stop()
        self._refresh_hotkey_controls()
        updated = replace(
            self.app_settings,
            global_hotkeys_enabled=enabled,
            pause_hotkey=self.pause_hotkey_var.get().strip(),
            window_hotkey=self.window_hotkey_var.get().strip(),
        )
        try:
            self.store.save(updated)
            self.app_settings = updated
        except (OSError, ValueError) as error:
            self.logger.error("Saving global hotkey preference failed: %s", error)
            messagebox.showwarning("设置未保存", "全局快捷键已生效，但设置未能保存。")

    def _on_floating_status_changed(self) -> None:
        enabled = self.floating_status_var.get()
        self.floating_status.set_enabled(enabled)
        updated = replace(self.app_settings, floating_status_enabled=enabled)
        try:
            self.store.save(updated)
            self.app_settings = updated
        except (OSError, ValueError) as error:
            self.logger.error("Saving floating status preference failed: %s", error)
            messagebox.showwarning("设置未保存", "悬浮计时条设置未能保存。")

    def _on_startup_changed(self) -> None:
        requested = STARTUP_OPTIONS.get(self.startup_var.get(), StartupMode.OFF)
        previous = self.startup_mode
        try:
            self.startup_manager.set_mode(requested)
        except OSError as error:
            self.logger.error("Updating Windows startup setting failed: %s", error)
            self.startup_var.set(
                next(
                    label
                    for label, mode in STARTUP_OPTIONS.items()
                    if mode is previous
                )
            )
            messagebox.showerror("开机启动设置失败", str(error))
            return
        self.startup_mode = requested

    def _open_v2_settings(self) -> None:
        if getattr(self, "v2_window", None) is not None:
            try:
                if self.v2_window.winfo_exists():
                    self.v2_window.deiconify()
                    self.v2_window.lift()
                    return
            except tk.TclError:
                pass

        window = tk.Toplevel(self.root)
        self.v2_window = window
        window.title("V2 节律设置")
        layout = v2_window_layout(window.winfo_screenwidth(), window.winfo_screenheight())
        window.geometry(layout.geometry)
        window.minsize(layout.min_width, layout.min_height)
        window.transient(self.root)
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

        boundaries = ttk.LabelFrame(
            body, text="阶段边界", padding=(10, 4), style="Settings.TLabelframe"
        )
        boundaries.grid(row=2, column=0, sticky="ew", pady=(0, 6))
        boundaries.columnconfigure(1, weight=1)
        for row, (label, variable) in enumerate(
            (
                ("锚定期结束", self.anchor_end_var),
                ("疲劳期开始", self.fatigue_start_var),
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

        intervals = ttk.LabelFrame(
            body,
            text="阶段随机间隔（分钟）",
            padding=(10, 4),
            style="Settings.TLabelframe",
        )
        intervals.grid(row=3, column=0, sticky="ew")
        intervals.columnconfigure((1, 2), weight=1)
        ttk.Label(intervals, text="阶段", style="Section.TLabel").grid(
            row=0, column=0, sticky="w", padx=(0, 12), pady=(0, 1)
        )
        ttk.Label(intervals, text="最小", style="Section.TLabel").grid(
            row=0, column=1, sticky="w", pady=(0, 1)
        )
        ttk.Label(intervals, text="最大", style="Section.TLabel").grid(
            row=0, column=2, sticky="w", padx=(8, 0), pady=(0, 1)
        )
        interval_rows = (
            ("锚定期", self.anchor_min_var, self.anchor_max_var),
            ("深度期", self.deep_min_var, self.deep_max_var),
            ("疲劳期", self.fatigue_min_var, self.fatigue_max_var),
        )
        for row, (label, minimum, maximum) in enumerate(interval_rows, start=1):
            ttk.Label(intervals, text=label).grid(
                row=row, column=0, sticky="w", padx=(0, 12), pady=1
            )
            ttk.Entry(intervals, textvariable=minimum, width=10).grid(
                row=row, column=1, sticky="ew", pady=1
            )
            ttk.Entry(intervals, textvariable=maximum, width=10).grid(
                row=row, column=2, sticky="ew", padx=(8, 0), pady=1
            )

        actions = ttk.Frame(body, style="App.TFrame")
        actions.grid(row=4, column=0, sticky="e", pady=(8, 0))
        ttk.Button(
            actions, text="恢复默认节律", command=self._reset_v2_defaults
        ).pack(side="left", padx=(0, 8))
        ttk.Button(
            actions, text="完成", style="Primary.TButton", command=self._close_v2_settings
        ).pack(side="left")
        window.protocol("WM_DELETE_WINDOW", self._close_v2_settings)

    def _close_v2_settings(self) -> None:
        window, self.v2_window = getattr(self, "v2_window", None), None
        if window is not None:
            try:
                window.destroy()
            except tk.TclError:
                pass
        self._refresh_algorithm_controls()

    def _current_audio_path(self) -> Path:
        value = self.settings_form.audio_value
        return (
            Path(self.settings_form.custom_audio_path)
            if value == "custom"
            else resource_path(value)
        )

    def _current_return_audio_path(self) -> Path:
        value = self.settings_form.return_audio_value
        return (
            Path(self.settings_form.return_custom_audio_path)
            if value == "custom"
            else resource_path(value)
        )

    def _play_ambient_selection(
        self,
        noise: str,
        tone: str,
        volume: float,
        on_complete: Callable[[bool], None] | None = None,
    ) -> None:
        if noise == "off" and tone == "off":
            self._stop_ambient_playback()
            if on_complete is not None:
                on_complete(True)
            return

        def completed(played: bool) -> None:
            if not played:
                messagebox.showwarning(
                    "背景音播放失败",
                    "无法启动所选背景音。选择已保留，程序会在下次操作时重试；详情请查看 Logs。",
                )
            if on_complete is not None:
                on_complete(played)

        self.ambient_tasks.request(noise, tone, volume, completed)

    def _preview_ambient(self) -> None:
        self._play_ambient_selection(
            self.settings_form.ambient_value,
            self.settings_form.solfeggio_value,
            self.settings_form.ambient_volume_fraction,
        )

    def _apply_runtime_ambient(self) -> None:
        noise = self.settings_form.ambient_value
        tone = self.settings_form.solfeggio_value
        volume = min(100, max(0, round(self.ambient_volume_var.get())))
        self._save_runtime_ambient_preferences()
        if noise != "off" or tone != "off":
            self.runtime_view.set_ambient_summary("正在准备背景音…")
        self._play_ambient_selection(
            noise,
            tone,
            volume / 100.0,
            lambda played: self._runtime_ambient_completed(
                noise, tone, volume, played
            ),
        )

    def _runtime_ambient_completed(
        self, noise: str, tone: str, volume: int, played: bool
    ) -> None:
        if played and self.session is not None and self.session.state is SessionState.PAUSED:
            self.audio.pause_ambient()
        if not played:
            self.runtime_view.set_ambient_summary(
                "播放失败 · 已保留选择，等待下次重试"
            )
        else:
            self.runtime_view.set_ambient_summary(
                format_ambient_summary(noise, tone, volume)
            )

    def _stop_ambient_playback(self) -> None:
        self.ambient_tasks.cancel()
        self.audio.stop_ambient()

    def _save_runtime_ambient_preferences(self) -> None:
        noise = self.settings_form.ambient_value
        tone = self.settings_form.solfeggio_value
        volume = min(100, max(0, round(self.ambient_volume_var.get())))

        updated = replace(
            self.app_settings,
            ambient_choice=noise,
            solfeggio_choice=tone,
            ambient_volume=volume,
        )
        self.app_settings = updated
        try:
            self.store.save(updated)
        except (OSError, ValueError) as error:
            self.logger.warning("Saving runtime ambient setting failed: %s", error)
        self.ambient_volume_label_var.set(f"{volume}%")
        self.runtime_view.set_ambient_summary(
            format_ambient_summary(noise, tone, volume)
        )

    def _on_runtime_ambient_volume_changed(self, value: str) -> None:
        volume = min(100, max(0, round(float(value))))
        self.ambient_volume_label_var.set(f"{volume}%")
        self.ambient_tasks.set_volume(volume / 100.0)
        self.audio.set_ambient_volume(volume / 100.0)
        self.runtime_view.set_ambient_summary(
            format_ambient_summary(
                self.settings_form.ambient_value,
                self.settings_form.solfeggio_value,
                volume,
            )
        )

    def _stop_runtime_ambient(self) -> None:
        self.ambient_var.set("关闭")
        self.solfeggio_var.set("关闭")
        self._apply_runtime_ambient()

    def _toggle_runtime_ambient_controls(self) -> None:
        self.runtime_view.toggle_ambient_controls()

    def _apply_runtime_window_layout(self) -> None:
        self.runtime_view.apply_window_layout()

    def _apply_break_prompt_window_layout(self) -> None:
        self.root.update_idletasks()
        window_layout = runtime_window_layout(
            self.root.winfo_screenwidth(),
            self.root.winfo_screenheight(),
            controls_expanded=False,
            minimum_content_height=self.break_prompt_frame.winfo_reqheight(),
        )
        self.root.minsize(window_layout.min_width, window_layout.min_height)
        self.root.geometry(window_layout.geometry)

    def _refresh_runtime_ambient_summary(self) -> None:
        self.runtime_view.set_ambient_summary(
            format_ambient_summary(
                self.settings_form.ambient_value,
                self.settings_form.solfeggio_value,
                round(self.ambient_volume_var.get()),
            )
        )

    def _on_ambient_volume_changed(self, value: str) -> None:
        volume = min(100, max(0, round(float(value))))
        self.ambient_volume_label_var.set(f"{volume}%")
        self.ambient_tasks.set_volume(volume / 100.0)
        self.audio.set_ambient_volume(volume / 100.0)

    def _choose_audio(self, is_return: bool) -> None:
        selected = filedialog.askopenfilename(
            title="选择回归专注铃" if is_return else "选择微休息开始铃",
            filetypes=[("音频文件", "*.wav *.ogg *.mp3")],
        )
        if selected:
            if is_return:
                self.settings_form.return_custom_audio_path = selected
                self.return_audio_var.set("自定义音频")
            else:
                self.settings_form.custom_audio_path = selected
                self.audio_var.set("自定义音频")

    def _test_audio(self, is_return: bool) -> None:
        path = self._current_return_audio_path() if is_return else self._current_audio_path()
        value = (
            self.settings_form.return_audio_value
            if is_return
            else self.settings_form.audio_value
        )
        if value == "custom" and not path.is_file():
            messagebox.showerror("音频错误", "请先选择有效的自定义音频文件。")
            return
        if not self.audio.play_bell(path):
            messagebox.showwarning(
                "音频播放失败",
                "所选音频无法播放，已尝试 Windows 系统提示音。详情请查看 Logs。",
            )
            return
        self._stop_audio_later(5)

    def _start_focus(self) -> None:
        try:
            settings = self.settings_form.build_session_settings()
        except ValueError as error:
            self.form_error.config(text=str(error))
            return
        if not self._confirm_reminder_coverage(settings):
            return
        self.form_error.config(text="")
        self.app_settings = self.settings_form.build_app_settings(
            self.app_settings, settings
        )
        try:
            self.store.save(self.app_settings)
        except OSError as error:
            self.logger.error("Saving settings failed: %s", error)
            messagebox.showwarning("配置未保存", "本次可以继续运行，但设置未能保存。")

        self.session_generation += 1
        self.session = FocusSession(settings, SystemRandom(), time.monotonic)
        self.session.start()
        self.floating_status.set_enabled(self.app_settings.floating_status_enabled)
        self.floating_status.begin_session()
        self._play_ambient_selection(
            self.app_settings.ambient_choice,
            self.app_settings.solfeggio_choice,
            self.app_settings.ambient_volume / 100.0,
        )
        self.settings_frame.pack_forget()
        self.break_prompt_frame.pack_forget()
        ambient_summary = format_ambient_summary(
            self.settings_form.ambient_value,
            self.settings_form.solfeggio_value,
            round(self.ambient_volume_var.get()),
        )
        self.runtime_view.show_focus(ambient_summary)
        self.runtime_view.invalidate()
        self._update_focus_display()
        self.logger.info(
            "Focus started: duration=%s mode=%s preset=%s",
            settings.focus_duration_sec,
            settings.algorithm_mode.value,
            settings.reminder_preset.value,
        )
        self._schedule_tick(self.session_generation)

    @staticmethod
    def _confirm_reminder_coverage(settings: SessionSettings) -> bool:
        warnings = reminder_coverage_warnings(settings)
        if not warnings:
            return True
        details = "\n".join(f"• {warning}" for warning in warnings)
        return messagebox.askyesno(
            "提醒可能过少",
            f"{details}\n\n仍要按当前设置开始专注吗？",
        )

    def _schedule_tick(self, generation: int) -> None:
        if self.tick_after_id is not None:
            self.root.after_cancel(self.tick_after_id)
        self.tick_after_id = self.root.after(
            self.TICK_MS, lambda: self._tick(generation)
        )

    def _tick(self, generation: int) -> None:
        self.tick_after_id = None
        if generation != self.session_generation or self.session is None:
            return
        for event in self.session.tick():
            if event.kind is RuntimeEventKind.REMINDER_DUE:
                self._show_reminder(event.phase)
            elif event.kind is RuntimeEventKind.SUSPEND_DETECTED:
                self._close_reminder(dismiss=False)
                self.audio.pause_ambient()
                self.runtime_view.set_pause_state(paused=True)
                messagebox.showinfo(
                    "专注已暂停",
                    "检测到电脑睡眠或长时间挂起。过期提醒已取消，请确认后继续。",
                )
            elif event.kind is RuntimeEventKind.SESSION_FINISHED:
                self._show_break_prompt()
                return
            elif event.kind is RuntimeEventKind.LONG_BREAK_FINISHED:
                self.audio.play_bell(self._current_return_audio_path())
                messagebox.showinfo("休息结束", "大休息结束，可以开始下一个周期。")
                self._return_to_settings()
                return
        if self.session.is_long_break:
            self._update_long_break_display()
        else:
            self._update_focus_display()
        if self.session.state not in {SessionState.IDLE, SessionState.BREAK_PROMPT, SessionState.SHUTTING_DOWN}:
            self._schedule_tick(generation)

    def _update_focus_display(self) -> None:
        if self.session is None:
            return
        timer_text = self._format_seconds(self.session.remaining_sec)
        phase = self.session.current_phase
        state_suffix = "（已暂停）" if self.session.state is SessionState.PAUSED else ""
        phase_text = f"{PHASE_NAMES[phase]}{state_suffix}"
        interval = self._phase_interval(phase)
        interval_text = format_reminder_status(
            interval.minimum_sec,
            interval.maximum_sec,
            self.app_settings.show_next_reminder,
            self.session.next_reminder_remaining_sec,
            adaptive_enabled=self.session.settings.adaptive_reminders_enabled,
        )
        feedback_text = format_feedback_summary(
            self.session.feedback_summary,
            self.session.settings.adaptive_reminders_enabled,
        )
        self.runtime_view.render(
            RuntimeDisplay(timer_text, phase_text, interval_text, feedback_text)
        )
        self.floating_status.update(timer_text, phase_text)

    def _phase_interval(self, phase: V2Phase | None) -> IntervalRange:
        assert self.session is not None
        settings = self.session.settings
        if phase is None:
            return settings.classic_interval
        if phase is V2Phase.ATTENTION_ANCHOR:
            return settings.v2.anchor_interval
        if phase is V2Phase.DEEP_FOCUS:
            return settings.v2.deep_focus_interval
        return settings.v2.fatigue_interval

    @staticmethod
    def _format_seconds(seconds: float) -> str:
        value = max(0, math.ceil(seconds))
        return f"{value // 60:02d}:{value % 60:02d}"

    def _toggle_pause(self) -> None:
        if self.session is None:
            return
        if self.session.is_long_break:
            if self.session.state is SessionState.LONG_BREAK:
                self.session.pause()
                self.runtime_view.set_pause_state(paused=True, long_break=True)
            elif self.session.state is SessionState.PAUSED:
                self.session.resume()
                self.runtime_view.set_pause_state(paused=False, long_break=True)
            self._update_long_break_display()
            return
        if self.session.state is SessionState.FOCUSING:
            reminder_was_visible = self.session.reminder_visible
            self.session.pause()
            if reminder_was_visible:
                self._close_reminder(dismiss=False)
            self.audio.pause_ambient()
            self.runtime_view.set_pause_state(paused=True)
        elif self.session.state is SessionState.PAUSED:
            self.session.resume()
            self.audio.resume_ambient()
            self.runtime_view.set_pause_state(paused=False)
        self._update_focus_display()

    def _stop_focus(self) -> None:
        if self.session is None:
            return
        if not messagebox.askyesno("停止当前周期", "确定停止并返回设置界面吗？"):
            return
        self.logger.info("Session stopped by user")
        self.session.stop()
        self._return_to_settings()

    def _show_break_prompt(self) -> None:
        self._close_reminder(dismiss=False)
        self.audio.stop_bell()
        self._stop_ambient_playback()
        self.floating_status.end_session()
        self.runtime_view.hide()
        self.break_prompt_frame.pack(fill="both", expand=True)
        self._apply_break_prompt_window_layout()
        self.logger.info("Focus completed; waiting for long-break confirmation")

    def _start_long_break(self) -> None:
        if self.session is None:
            return
        try:
            duration = SettingsForm.parse_minutes(
                self.long_break_var.get(), "大休息"
            )
        except ValueError as error:
            messagebox.showerror("输入错误", str(error))
            return
        self.session.start_long_break(duration)
        self.break_prompt_frame.pack_forget()
        self.runtime_view.show_long_break()
        self.runtime_view.invalidate()
        self._update_long_break_display()
        self._schedule_tick(self.session_generation)

    def _update_long_break_display(self) -> None:
        if self.session is None:
            return
        remaining = self.session.long_break_remaining_sec
        timer_text = self._format_seconds(remaining)
        phase_text = "大休息（已暂停）" if self.session.state is SessionState.PAUSED else "大休息"
        self.runtime_view.render(
            RuntimeDisplay(
                timer_text,
                phase_text,
                "休息期间不会产生随机提醒",
            )
        )

    def _skip_long_break(self) -> None:
        if self.session is not None:
            self.session.stop()
        self._return_to_settings()

    def _return_to_settings(self) -> None:
        self.session_generation += 1
        if self.tick_after_id is not None:
            self.root.after_cancel(self.tick_after_id)
            self.tick_after_id = None
        self._close_reminder(dismiss=False)
        self.audio.stop_bell()
        self._stop_ambient_playback()
        self.floating_status.end_session()
        self.runtime_view.hide()
        self.break_prompt_frame.pack_forget()
        self.settings_frame.pack(fill="both", expand=True)
        self.runtime_view.invalidate()
        self._apply_settings_window_layout()
        self.root.deiconify()

    def _show_reminder(self, phase: V2Phase | None) -> None:
        if self.session is None:
            return
        preset = self.session.settings.reminder_preset
        adaptive = self.session.settings.adaptive_reminders_enabled
        self.logger.info(
            "Reminder triggered: phase=%s preset=%s adaptive=%s",
            phase.value if phase is not None else "classic",
            preset.value,
            adaptive,
        )
        if not self.session.settings.break_countdown_enabled:
            if adaptive:
                self._show_banner("我还在原任务上吗？", 8)
                return
            self.tray.notify("CountdownApp", "微休息提醒：放松视线，确认当前任务。")
            self.audio.play_bell(self._current_audio_path())
            self._stop_audio_later(5)
            self.session.dismiss_reminder()
            return
        if phase is V2Phase.DEEP_FOCUS:
            if adaptive:
                self._show_banner("深度专注：放松视线，确认任务方向。", 8)
                return
            notified = self.tray.notify("CountdownApp", "深度专注提醒：放松视线，确认任务方向。")
            self.audio.play_bell(self._current_audio_path())
            self._stop_audio_later(5)
            if notified:
                self.session.dismiss_reminder()
            else:
                self._show_banner("深度专注：放松视线，确认任务方向。", 5)
            return
        if phase is V2Phase.ATTENTION_ANCHOR:
            duration = 5 if preset is ReminderPreset.BALANCED else self.session.settings.microbreak_duration_sec
            if adaptive:
                duration = max(8, duration)
            self._show_banner("我还在原任务上吗？", duration)
            return
        self._show_overlay(self.session.settings.microbreak_duration_sec, preset)

    def _show_banner(self, message: str, duration_sec: int) -> None:
        adaptive = bool(
            self.session is not None
            and self.session.settings.adaptive_reminders_enabled
        )
        self.reminder_view.show_banner(
            message,
            duration_sec,
            adaptive,
            self._handle_reminder_result,
        )
        self.audio.play_bell(self._current_audio_path())

    def _show_overlay(self, duration_sec: int, preset: ReminderPreset) -> None:
        adaptive = bool(
            self.session is not None
            and self.session.settings.adaptive_reminders_enabled
        )
        self.reminder_view.show_overlay(
            duration_sec,
            preset,
            adaptive,
            self._handle_reminder_result,
        )
        self.audio.play_bell(self._current_audio_path())

    def _handle_reminder_result(self, result: ReminderResult) -> None:
        if result.kind is ReminderResultKind.FEEDBACK and result.feedback is not None:
            self._submit_feedback(result.feedback)
            return
        self._close_reminder(
            completed_automatically=result.kind is ReminderResultKind.COMPLETED
        )

    def _submit_feedback(self, feedback: AttentionFeedback) -> None:
        if self.session is None or not self.session.record_feedback(feedback):
            return
        self.logger.info("Attention feedback recorded: %s", feedback.value)
        self._close_reminder(dismiss=False)
        self._update_focus_display()

    def _close_reminder(
        self,
        dismiss: bool = True,
        completed_automatically: bool = False,
    ) -> None:
        self.reminder_view.close()
        if self.audio_after_id is not None:
            try:
                self.root.after_cancel(self.audio_after_id)
            except tk.TclError:
                pass
            self.audio_after_id = None
        self.audio.stop_bell()
        if dismiss and self.session is not None:
            self.session.dismiss_reminder()
        countdown_enabled = bool(
            self.session is not None and self.session.settings.break_countdown_enabled
        )
        if should_play_return_bell(
            countdown_enabled=countdown_enabled,
            completed_automatically=completed_automatically,
        ):
            self.audio.play_bell(self._current_return_audio_path())
            self._stop_audio_later(5)

    def _stop_audio_later(self, seconds: int) -> None:
        if self.audio_after_id is not None:
            try:
                self.root.after_cancel(self.audio_after_id)
            except tk.TclError:
                pass
        self.audio_after_id = self.root.after(seconds * 1000, self._stop_scheduled_audio)

    def _stop_scheduled_audio(self) -> None:
        self.audio_after_id = None
        self.audio.stop_bell()

    def _minimize_to_tray(self) -> None:
        if self.tray.available:
            if self.session is None or self.session.state is SessionState.IDLE:
                self._stop_ambient_playback()
            self.root.withdraw()
        else:
            messagebox.showwarning("托盘不可用", "系统托盘初始化失败，窗口不能隐藏。")

    def _on_window_close(self) -> None:
        active = self.session is not None and self.session.state not in {
            SessionState.IDLE,
            SessionState.SHUTTING_DOWN,
        }
        if self.close_to_tray_var.get() and self.tray.available:
            self.root.withdraw()
            return
        if active and not messagebox.askyesno("退出程序", "当前周期仍在运行，确定退出吗？"):
            return
        self._shutdown()

    def _poll_tray(self) -> None:
        self.tray_after_id = None
        self.hotkeys.poll()
        try:
            while True:
                self.gui_callbacks.get_nowait()()
        except queue.Empty:
            pass
        try:
            while True:
                command = self.tray_commands.get_nowait()
                if command == "show":
                    self.root.deiconify()
                    self.root.lift()
                elif command == "toggle_window":
                    if self.root.state() == "withdrawn":
                        self.root.deiconify()
                        self.root.lift()
                    else:
                        self.root.withdraw()
                elif command == "pause":
                    self._toggle_pause()
                elif command == "stop":
                    self._stop_focus()
                elif command == "quit":
                    if self.session is None or self.session.state is SessionState.IDLE or messagebox.askyesno(
                        "退出程序", "当前周期仍在运行，确定退出吗？"
                    ):
                        self._shutdown()
                        return
        except queue.Empty:
            pass
        try:
            self.tray_after_id = self.root.after(self.TRAY_POLL_MS, self._poll_tray)
        except tk.TclError:
            pass

    def _shutdown(self) -> None:
        self.logger.info("Application shutting down")
        self.session_generation += 1
        if self.session is not None:
            self.session.shutdown()
        if self.tick_after_id is not None:
            try:
                self.root.after_cancel(self.tick_after_id)
            except tk.TclError:
                pass
            self.tick_after_id = None
        if self.tray_after_id is not None:
            try:
                self.root.after_cancel(self.tray_after_id)
            except tk.TclError:
                pass
            self.tray_after_id = None
        self._close_reminder(dismiss=False)
        self.floating_status.close()
        self.ambient_tasks.close()
        self.audio.close()
        self.hotkeys.stop()
        self.tray.stop()
        try:
            self.root.destroy()
        except tk.TclError:
            pass


def run() -> None:
    guard = SingleInstanceGuard()
    try:
        acquired = guard.acquire()
    except OSError as error:
        show_native_message(
            "CountdownApp 启动失败",
            f"无法建立单实例保护：{error}",
            error=True,
        )
        return
    if not acquired:
        show_native_message(
            "CountdownApp 已在运行",
            "程序已经启动，主界面可能已隐藏在系统托盘中。",
        )
        return

    logger = configure_logging()
    root: tk.Tk | None = None
    try:
        root = tk.Tk()

        def report_callback_exception(
            exception_type: type[BaseException],
            error: BaseException,
            traceback: TracebackType | None,
        ) -> None:
            logger.error(
                "Unhandled Tk callback exception",
                exc_info=(exception_type, error, traceback),
            )
            messagebox.showerror(
                "CountdownApp 发生错误",
                f"操作执行失败：{error}\n\n详情已写入 Logs。",
                parent=root,
            )

        root.report_callback_exception = report_callback_exception
        CountdownApp(root)
        root.mainloop()
    except Exception as error:
        logger.exception("Fatal application startup error")
        show_native_message(
            "CountdownApp 启动失败",
            f"程序无法启动：{error}\n\n请查看安装目录中的 Logs。",
            error=True,
        )
    finally:
        if root is not None:
            try:
                root.destroy()
            except tk.TclError:
                pass
        guard.release()
