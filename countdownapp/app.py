from __future__ import annotations

import math
import queue
import sys
import time
import tkinter as tk
from dataclasses import replace
from pathlib import Path
from secrets import SystemRandom
from tkinter import filedialog, messagebox, ttk

from .audio import AudioEngine, should_play_return_bell
from .config import AppSettings, ConfigStore
from .domain import (
    AlgorithmMode,
    IntervalRange,
    ReminderPreset,
    SessionSettings,
    SessionState,
    V2Phase,
    V2Settings,
    validate_settings,
)
from .floating import FloatingStatusController, TkFloatingStatusView
from .hotkeys import GlobalHotkeyService
from .logging_config import configure_logging
from .presentation import RenderCache, format_reminder_status
from .resources import install_dir, resource_path
from .session import FocusSession, RuntimeEventKind
from .startup import StartupManager, StartupMode, should_start_hidden
from .tray import TrayService


PHASE_NAMES = {
    None: "Classic",
    V2Phase.ATTENTION_ANCHOR: "注意力锚定期",
    V2Phase.DEEP_FOCUS: "深度专注期",
    V2Phase.FATIGUE_SUPPORT: "疲劳维护期",
}

AUDIO_OPTIONS = {
    "提示音 0": "0.wav",
    "提示音 1": "1.wav",
    "提示音 2": "2.wav",
    "提示音 3": "3.wav",
    "提示音 4": "4.mp3",
    "自定义音频": "custom",
}

STARTUP_OPTIONS = {
    "关闭": StartupMode.OFF,
    "开机启动（显示主界面）": StartupMode.VISIBLE,
    "开机静默启动（仅显示托盘图标）": StartupMode.SILENT,
}

NOISE_OPTIONS = {
    "关闭": "off",
    "白噪音": "white",
    "粉红噪音": "pink",
    "棕噪音（低频更强）": "brown",
    "灰噪音（近似等响度）": "grey",
}

SOLFEGGIO_OPTIONS = {
    "关闭": "off",
    "Solfeggio 174 Hz": "tone:174",
    "Solfeggio 285 Hz": "tone:285",
    "Solfeggio 396 Hz": "tone:396",
    "Solfeggio 417 Hz": "tone:417",
    "Solfeggio 528 Hz": "tone:528",
    "Solfeggio 639 Hz": "tone:639",
    "Solfeggio 741 Hz": "tone:741",
    "Solfeggio 852 Hz": "tone:852",
    "Solfeggio 963 Hz": "tone:963",
}


class CountdownApp:
    TICK_MS = 500
    TRAY_POLL_MS = 250
    OVERLAY_TICK_MS = 200

    def __init__(self, root: tk.Tk):
        self.root = root
        self.logger = configure_logging()
        self.store = ConfigStore()
        self.app_settings = self.store.migrate_legacy(
            [install_dir() / "settings.ini", Path.cwd() / "settings.ini"]
        )
        self.audio = AudioEngine(logger=self.logger)
        self.startup_manager = StartupManager()
        try:
            self.startup_mode = self.startup_manager.get_mode()
        except OSError as error:
            self.logger.warning("Reading Windows startup setting failed: %s", error)
            self.startup_mode = StartupMode.OFF
        self.session: FocusSession | None = None
        self.session_generation = 0
        self.tick_after_id: str | None = None
        self.tray_after_id: str | None = None
        self.reminder_after_id: str | None = None
        self.audio_after_id: str | None = None
        self.reminder_window: tk.Toplevel | None = None
        self.render_cache = RenderCache()

        self.tray_commands: "queue.Queue[str]" = queue.Queue()
        self.tray = TrayService(resource_path("clock_icon.ico"), self.tray_commands, self.logger)
        self.hotkeys = GlobalHotkeyService(self.tray_commands, self.logger)
        self.floating_status = FloatingStatusController(
            lambda on_hide: TkFloatingStatusView(self.root, on_hide)
        )

        self._configure_root()
        self._build_ui()
        self._load_form(self.app_settings)
        self.floating_status.set_enabled(self.app_settings.floating_status_enabled)
        hotkey_start_failed = bool(
            self.app_settings.global_hotkeys_enabled and not self.hotkeys.start()
        )
        if hotkey_start_failed:
            self.global_hotkeys_var.set(False)
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
        if hotkey_start_failed and not start_hidden:
            self.root.after(
                0,
                lambda: messagebox.showwarning(
                    "全局快捷键不可用",
                    "快捷键已被其他程序占用，功能已自动关闭。",
                ),
            )
        self.tray_after_id = self.root.after(self.TRAY_POLL_MS, self._poll_tray)
        self.logger.info("Application started")

    def _configure_root(self) -> None:
        self.root.title("CountdownApp V2")
        self.root.geometry("760x760")
        self.root.minsize(700, 620)
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
            "Title.TLabel", background=background, foreground=text,
            font=("Microsoft YaHei UI", 22, "bold")
        )
        style.configure(
            "Subtitle.TLabel", background=background, foreground=muted,
            font=("Microsoft YaHei UI", 10)
        )
        style.configure(
            "Timer.TLabel", background=background, foreground=text,
            font=("Microsoft YaHei UI", 50, "bold")
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

    def _build_ui(self) -> None:
        self.settings_frame = ttk.Frame(self.root, padding=(26, 20), style="App.TFrame")
        self.running_frame = ttk.Frame(self.root, padding=30, style="App.TFrame")
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

        self.total_var = tk.StringVar()
        self.algorithm_var = tk.StringVar()
        self.classic_min_var = tk.StringVar()
        self.classic_max_var = tk.StringVar()
        self.anchor_end_var = tk.StringVar()
        self.fatigue_start_var = tk.StringVar()
        self.anchor_min_var = tk.StringVar()
        self.anchor_max_var = tk.StringVar()
        self.deep_min_var = tk.StringVar()
        self.deep_max_var = tk.StringVar()
        self.fatigue_min_var = tk.StringVar()
        self.fatigue_max_var = tk.StringVar()
        self.preset_var = tk.StringVar()
        self.microbreak_var = tk.StringVar()
        self.break_countdown_var = tk.BooleanVar()
        self.long_break_var = tk.StringVar()
        self.audio_var = tk.StringVar()
        self.return_audio_var = tk.StringVar()
        self.ambient_var = tk.StringVar()
        self.solfeggio_var = tk.StringVar()
        self.ambient_volume_var = tk.DoubleVar()
        self.ambient_volume_label_var = tk.StringVar()
        self.close_to_tray_var = tk.BooleanVar()
        self.show_next_reminder_var = tk.BooleanVar()
        self.global_hotkeys_var = tk.BooleanVar()
        self.floating_status_var = tk.BooleanVar()
        self.startup_var = tk.StringVar()
        self.custom_audio_path = ""
        self.return_custom_audio_path = ""

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
            wraplength=430,
            justify="left",
        )
        self.v2_summary_label.grid(row=10, column=0, columnspan=2, sticky="w", pady=5)
        self.v2_settings_button = ttk.Button(
            form, text="调整 V2", command=self._open_v2_settings
        )
        self.v2_settings_button.grid(row=10, column=2, sticky="e", pady=5)
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
            form, text="更多设置 ▾", command=self._toggle_more_settings
        )
        self.more_button.grid(row=11, column=0, columnspan=3, pady=(8, 2))
        self.more_frame = ttk.Frame(form, padding=(0, 8, 0, 0), style="Form.TFrame")
        self.more_frame.columnconfigure(1, weight=1)

        ttk.Label(self.more_frame, text="提醒强度", style="Form.TLabel").grid(
            row=0, column=0, sticky="e", pady=4
        )
        ttk.Combobox(
            self.more_frame,
            textvariable=self.preset_var,
            values=("平衡", "强干预"),
            state="readonly",
            width=18,
        ).grid(row=0, column=1, sticky="ew", padx=(12, 8), pady=4)

        ttk.Label(self.more_frame, text="微休息开始铃", style="Form.TLabel").grid(
            row=1, column=0, sticky="e", pady=4
        )
        ttk.Combobox(
            self.more_frame,
            textvariable=self.audio_var,
            values=tuple(AUDIO_OPTIONS),
            state="readonly",
            width=18,
        ).grid(row=1, column=1, sticky="ew", padx=(12, 8), pady=4)
        ttk.Button(
            self.more_frame, text="试听", command=lambda: self._test_audio(False)
        ).grid(row=1, column=2, padx=4)
        ttk.Button(
            self.more_frame, text="选择文件", command=lambda: self._choose_audio(False)
        ).grid(row=1, column=3)

        ttk.Label(self.more_frame, text="回归专注铃", style="Form.TLabel").grid(
            row=2, column=0, sticky="e", pady=4
        )
        ttk.Combobox(
            self.more_frame,
            textvariable=self.return_audio_var,
            values=tuple(AUDIO_OPTIONS),
            state="readonly",
            width=18,
        ).grid(row=2, column=1, sticky="ew", padx=(12, 8), pady=4)
        ttk.Button(
            self.more_frame, text="试听", command=lambda: self._test_audio(True)
        ).grid(row=2, column=2, padx=4)
        ttk.Button(
            self.more_frame, text="选择文件", command=lambda: self._choose_audio(True)
        ).grid(row=2, column=3)

        ttk.Label(self.more_frame, text="噪音底色", style="Form.TLabel").grid(
            row=3, column=0, sticky="e", pady=(12, 4)
        )
        ttk.Combobox(
            self.more_frame,
            textvariable=self.ambient_var,
            values=tuple(NOISE_OPTIONS),
            state="readonly",
            width=24,
        ).grid(row=3, column=1, sticky="ew", padx=(12, 8), pady=(12, 4))
        ttk.Button(
            self.more_frame, text="试听组合", command=self._preview_ambient
        ).grid(row=3, column=2, padx=4, pady=(12, 4))
        ttk.Button(
            self.more_frame, text="停止", command=self.audio.stop_ambient
        ).grid(row=3, column=3, pady=(12, 4))

        ttk.Label(self.more_frame, text="Solfeggio 频率", style="Form.TLabel").grid(
            row=4, column=0, sticky="e", pady=4
        )
        ttk.Combobox(
            self.more_frame,
            textvariable=self.solfeggio_var,
            values=tuple(SOLFEGGIO_OPTIONS),
            state="readonly",
            width=24,
        ).grid(row=4, column=1, columnspan=3, sticky="ew", padx=(12, 0), pady=4)

        ttk.Label(self.more_frame, text="背景音量", style="Form.TLabel").grid(
            row=5, column=0, sticky="e", pady=4
        )
        ttk.Scale(
            self.more_frame,
            from_=0,
            to=100,
            variable=self.ambient_volume_var,
            command=self._on_ambient_volume_changed,
        ).grid(row=5, column=1, columnspan=2, sticky="ew", padx=(12, 8), pady=4)
        ttk.Label(
            self.more_frame,
            textvariable=self.ambient_volume_label_var,
            style="FormHint.TLabel",
            width=5,
        ).grid(row=5, column=3, sticky="w")

        ttk.Separator(self.more_frame).grid(
            row=6, column=0, columnspan=4, sticky="ew", pady=10
        )
        ttk.Checkbutton(
            self.more_frame,
            text="显示下一次提醒的剩余时间（默认遮蔽，减少等待焦虑）",
            variable=self.show_next_reminder_var,
            style="Form.TCheckbutton",
        ).grid(row=7, column=0, columnspan=4, sticky="w", pady=4)
        ttk.Checkbutton(
            self.more_frame,
            text="显示置顶悬浮计时条（右键或 × 可临时隐藏）",
            variable=self.floating_status_var,
            command=self._on_floating_status_changed,
            style="Form.TCheckbutton",
        ).grid(row=8, column=0, columnspan=4, sticky="w", pady=4)
        ttk.Checkbutton(
            self.more_frame,
            text="启用全局快捷键（Alt+Shift+P 暂停；Alt+Shift+O 显示/隐藏）",
            variable=self.global_hotkeys_var,
            command=self._on_global_hotkeys_changed,
            style="Form.TCheckbutton",
        ).grid(row=9, column=0, columnspan=4, sticky="w", pady=4)
        ttk.Checkbutton(
            self.more_frame,
            text="关闭主窗口时隐藏到托盘（任务栏不显示）",
            variable=self.close_to_tray_var,
            command=self._on_close_to_tray_changed,
            style="Form.TCheckbutton",
        ).grid(row=10, column=0, columnspan=4, sticky="w", pady=4)
        ttk.Label(
            self.more_frame,
            text="开机启动",
            style="Form.TLabel",
        ).grid(row=11, column=0, sticky="e", pady=4)
        startup_box = ttk.Combobox(
            self.more_frame,
            textvariable=self.startup_var,
            values=tuple(STARTUP_OPTIONS),
            state="readonly",
            width=30,
        )
        startup_box.grid(row=11, column=1, columnspan=3, sticky="ew", padx=(12, 0), pady=4)
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

        ttk.Label(self.running_frame, text="剩余时间", style="Title.TLabel").pack(pady=(30, 10))
        self.timer_label = ttk.Label(self.running_frame, text="00:00", style="Timer.TLabel")
        self.timer_label.pack(pady=10)
        self.phase_label = ttk.Label(self.running_frame, text="", style="Phase.TLabel")
        self.phase_label.pack(pady=8)
        self.interval_label = ttk.Label(self.running_frame, text="", style="Phase.TLabel")
        self.interval_label.pack(pady=4)
        running_actions = ttk.Frame(self.running_frame)
        running_actions.pack(pady=25)
        self.pause_button = ttk.Button(running_actions, text="暂停", command=self._toggle_pause)
        self.pause_button.pack(side="left", padx=6)
        ttk.Button(running_actions, text="停止", command=self._stop_focus).pack(side="left", padx=6)
        ttk.Button(running_actions, text="最小化到托盘", command=self._minimize_to_tray).pack(
            side="left", padx=6
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
        session = settings.session
        self.total_var.set(self._number(session.focus_duration_sec / 60))
        self.algorithm_var.set("V2" if session.algorithm_mode is AlgorithmMode.V2 else "Classic")
        self.classic_min_var.set(self._number(session.classic_interval.minimum_sec / 60))
        self.classic_max_var.set(self._number(session.classic_interval.maximum_sec / 60))
        self.anchor_end_var.set(self._number(session.v2.anchor_end_sec / 60))
        self.fatigue_start_var.set(self._number(session.v2.fatigue_start_sec / 60))
        self.anchor_min_var.set(self._number(session.v2.anchor_interval.minimum_sec / 60))
        self.anchor_max_var.set(self._number(session.v2.anchor_interval.maximum_sec / 60))
        self.deep_min_var.set(self._number(session.v2.deep_focus_interval.minimum_sec / 60))
        self.deep_max_var.set(self._number(session.v2.deep_focus_interval.maximum_sec / 60))
        self.fatigue_min_var.set(self._number(session.v2.fatigue_interval.minimum_sec / 60))
        self.fatigue_max_var.set(self._number(session.v2.fatigue_interval.maximum_sec / 60))
        self.preset_var.set("强干预" if session.reminder_preset is ReminderPreset.STRONG else "平衡")
        self.microbreak_var.set(str(session.microbreak_duration_sec))
        self.break_countdown_var.set(session.break_countdown_enabled)
        self.long_break_var.set(self._number(session.long_break_duration_sec / 60))
        selected_name = next(
            (name for name, value in AUDIO_OPTIONS.items() if value == settings.audio_choice),
            "提示音 0",
        )
        self.audio_var.set(selected_name)
        self.custom_audio_path = settings.custom_audio_path
        return_selected_name = next(
            (name for name, value in AUDIO_OPTIONS.items() if value == settings.return_audio_choice),
            "提示音 1",
        )
        self.return_audio_var.set(return_selected_name)
        self.return_custom_audio_path = settings.return_custom_audio_path
        self.ambient_var.set(
            next(
                (
                    name
                    for name, value in NOISE_OPTIONS.items()
                    if value == settings.ambient_choice
                ),
                "关闭",
            )
        )
        self.solfeggio_var.set(
            next(
                (
                    name
                    for name, value in SOLFEGGIO_OPTIONS.items()
                    if value == settings.solfeggio_choice
                ),
                "关闭",
            )
        )
        self.ambient_volume_var.set(settings.ambient_volume)
        self.ambient_volume_label_var.set(f"{settings.ambient_volume}%")
        self.close_to_tray_var.set(settings.close_to_tray)
        self.show_next_reminder_var.set(settings.show_next_reminder)
        self.global_hotkeys_var.set(settings.global_hotkeys_enabled)
        self.floating_status_var.set(settings.floating_status_enabled)
        self.startup_var.set(
            next(
                label
                for label, mode in STARTUP_OPTIONS.items()
                if mode is self.startup_mode
            )
        )
        self._refresh_algorithm_controls()

    @staticmethod
    def _number(value: float) -> str:
        return str(int(value)) if float(value).is_integer() else f"{value:.2f}".rstrip("0")

    def _set_duration_preset(self, minutes: int) -> None:
        self.total_var.set(str(minutes))
        self.algorithm_var.set("V2" if minutes >= 60 else "Classic")
        self._reset_v2_defaults()

    def _reset_v2_defaults(self) -> None:
        try:
            total = self._minutes(self.total_var.get(), "总专注时间")
        except ValueError as error:
            self.form_error.config(text=str(error))
            return
        self.anchor_end_var.set(self._number(total / 3 / 60))
        self.fatigue_start_var.set(self._number(total * 13 / 18 / 60))
        self.anchor_min_var.set("4")
        self.anchor_max_var.set("7")
        self.deep_min_var.set("10")
        self.deep_max_var.set("15")
        self.fatigue_min_var.set("5")
        self.fatigue_max_var.set("8")
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
            self.more_frame.grid(row=12, column=0, columnspan=3, sticky="ew")
            self.more_button.config(text="收起更多设置 ▴")
        else:
            self.more_frame.grid_remove()
            self.more_button.config(text="更多设置 ▾")

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

    def _on_global_hotkeys_changed(self) -> None:
        enabled = self.global_hotkeys_var.get()
        if enabled and not self.hotkeys.start():
            self.global_hotkeys_var.set(False)
            enabled = False
            messagebox.showwarning(
                "全局快捷键不可用",
                "Alt+Shift+P 或 Alt+Shift+O 已被其他程序占用，未启用快捷键。",
            )
        elif not enabled:
            self.hotkeys.stop()
        updated = replace(self.app_settings, global_hotkeys_enabled=enabled)
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
        window.geometry("580x500")
        window.minsize(540, 460)
        window.transient(self.root)
        body = ttk.Frame(window, padding=24, style="App.TFrame")
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)

        ttk.Label(body, text="V2 节律设置", style="Title.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 4)
        )
        ttk.Label(
            body,
            text="主页面的最小/最大间隔对应注意力锚定期。这里可以调整全部阶段。",
            style="Subtitle.TLabel",
            wraplength=500,
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 16))

        rows = (
            ("锚定期结束（分钟）", self.anchor_end_var),
            ("疲劳期开始（分钟）", self.fatigue_start_var),
            ("锚定期间隔（分钟）", (self.anchor_min_var, self.anchor_max_var)),
            ("深度期间隔（分钟）", (self.deep_min_var, self.deep_max_var)),
            ("疲劳期间隔（分钟）", (self.fatigue_min_var, self.fatigue_max_var)),
        )
        for row, (label, variables) in enumerate(rows, start=2):
            ttk.Label(body, text=label).grid(row=row, column=0, sticky="e", pady=7)
            if isinstance(variables, tuple):
                interval_box = ttk.Frame(body, style="App.TFrame")
                interval_box.grid(row=row, column=1, sticky="w", padx=(12, 0))
                ttk.Entry(interval_box, textvariable=variables[0], width=10).pack(side="left")
                ttk.Label(interval_box, text="—").pack(side="left", padx=7)
                ttk.Entry(interval_box, textvariable=variables[1], width=10).pack(side="left")
            else:
                ttk.Entry(body, textvariable=variables, width=22).grid(
                    row=row, column=1, sticky="ew", padx=(12, 0), pady=7
                )

        actions = ttk.Frame(body, style="App.TFrame")
        actions.grid(row=7, column=0, columnspan=2, pady=(20, 0))
        ttk.Button(
            actions, text="恢复默认节律", command=self._reset_v2_defaults
        ).pack(side="left", padx=5)
        ttk.Button(
            actions, text="完成", style="Primary.TButton", command=self._close_v2_settings
        ).pack(side="left", padx=5)
        window.protocol("WM_DELETE_WINDOW", self._close_v2_settings)

    def _close_v2_settings(self) -> None:
        window, self.v2_window = getattr(self, "v2_window", None), None
        if window is not None:
            try:
                window.destroy()
            except tk.TclError:
                pass
        self._refresh_algorithm_controls()

    def _build_settings_from_form(self) -> SessionSettings:
        total = self._minutes(self.total_var.get(), "总专注时间")
        mode = AlgorithmMode.V2 if self.algorithm_var.get() == "V2" else AlgorithmMode.CLASSIC
        settings = SessionSettings(
            focus_duration_sec=total,
            algorithm_mode=mode,
            classic_interval=IntervalRange(
                self._minutes(self.classic_min_var.get(), "Classic 最小间隔"),
                self._minutes(self.classic_max_var.get(), "Classic 最大间隔"),
            ),
            v2=V2Settings(
                anchor_end_sec=self._minutes(self.anchor_end_var.get(), "锚定期结束"),
                fatigue_start_sec=self._minutes(self.fatigue_start_var.get(), "疲劳期开始"),
                anchor_interval=IntervalRange(
                    self._minutes(self.anchor_min_var.get(), "锚定期最小间隔"),
                    self._minutes(self.anchor_max_var.get(), "锚定期最大间隔"),
                ),
                deep_focus_interval=IntervalRange(
                    self._minutes(self.deep_min_var.get(), "深度期最小间隔"),
                    self._minutes(self.deep_max_var.get(), "深度期最大间隔"),
                ),
                fatigue_interval=IntervalRange(
                    self._minutes(self.fatigue_min_var.get(), "疲劳期最小间隔"),
                    self._minutes(self.fatigue_max_var.get(), "疲劳期最大间隔"),
                ),
            ),
            reminder_preset=(
                ReminderPreset.STRONG if self.preset_var.get() == "强干预" else ReminderPreset.BALANCED
            ),
            microbreak_duration_sec=self._positive_int(self.microbreak_var.get(), "微休息"),
            break_countdown_enabled=self.break_countdown_var.get(),
            long_break_duration_sec=self._minutes(self.long_break_var.get(), "大休息"),
        )
        errors = validate_settings(settings)
        if errors:
            raise ValueError("\n".join(errors))
        if AUDIO_OPTIONS.get(self.audio_var.get()) == "custom":
            custom = Path(self.custom_audio_path)
            if not custom.is_file() or custom.suffix.lower() not in {".wav", ".ogg", ".mp3"}:
                raise ValueError("自定义开始铃不存在或格式不受支持。")
        if AUDIO_OPTIONS.get(self.return_audio_var.get()) == "custom":
            custom = Path(self.return_custom_audio_path)
            if not custom.is_file() or custom.suffix.lower() not in {".wav", ".ogg", ".mp3"}:
                raise ValueError("自定义回归铃不存在或格式不受支持。")
        return settings

    @staticmethod
    def _minutes(value: str, label: str) -> int:
        try:
            number = float(value.strip())
        except (TypeError, ValueError):
            raise ValueError(f"{label}必须是数字。") from None
        if not math.isfinite(number) or number <= 0:
            raise ValueError(f"{label}必须大于 0。")
        return max(1, round(number * 60))

    @staticmethod
    def _positive_int(value: str, label: str) -> int:
        try:
            number = int(value.strip())
        except (TypeError, ValueError):
            raise ValueError(f"{label}必须是整数。") from None
        if number <= 0:
            raise ValueError(f"{label}必须大于 0。")
        return number

    def _current_audio_value(self) -> str:
        return AUDIO_OPTIONS.get(self.audio_var.get(), "0.wav")

    def _current_audio_path(self) -> Path:
        value = self._current_audio_value()
        return Path(self.custom_audio_path) if value == "custom" else resource_path(value)

    def _current_return_audio_value(self) -> str:
        return AUDIO_OPTIONS.get(self.return_audio_var.get(), "1.wav")

    def _current_return_audio_path(self) -> Path:
        value = self._current_return_audio_value()
        return (
            Path(self.return_custom_audio_path)
            if value == "custom"
            else resource_path(value)
        )

    def _current_ambient_value(self) -> str:
        return NOISE_OPTIONS.get(self.ambient_var.get(), "off")

    def _current_solfeggio_value(self) -> str:
        return SOLFEGGIO_OPTIONS.get(self.solfeggio_var.get(), "off")

    def _ambient_volume(self) -> float:
        return min(1.0, max(0.0, self.ambient_volume_var.get() / 100.0))

    def _preview_ambient(self) -> None:
        self.audio.play_ambient(
            self._current_ambient_value(),
            self._current_solfeggio_value(),
            self._ambient_volume(),
        )

    def _on_ambient_volume_changed(self, value: str) -> None:
        volume = min(100, max(0, round(float(value))))
        self.ambient_volume_label_var.set(f"{volume}%")
        self.audio.set_ambient_volume(volume / 100.0)

    def _choose_audio(self, is_return: bool) -> None:
        selected = filedialog.askopenfilename(
            title="选择回归专注铃" if is_return else "选择微休息开始铃",
            filetypes=[("音频文件", "*.wav *.ogg *.mp3")],
        )
        if selected:
            if is_return:
                self.return_custom_audio_path = selected
                self.return_audio_var.set("自定义音频")
            else:
                self.custom_audio_path = selected
                self.audio_var.set("自定义音频")

    def _test_audio(self, is_return: bool) -> None:
        path = self._current_return_audio_path() if is_return else self._current_audio_path()
        value = self._current_return_audio_value() if is_return else self._current_audio_value()
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
            settings = self._build_settings_from_form()
        except ValueError as error:
            self.form_error.config(text=str(error))
            return
        self.form_error.config(text="")
        self.app_settings = AppSettings(
            session=settings,
            audio_choice=self._current_audio_value(),
            custom_audio_path=self.custom_audio_path,
            return_audio_choice=self._current_return_audio_value(),
            return_custom_audio_path=self.return_custom_audio_path,
            ambient_choice=self._current_ambient_value(),
            solfeggio_choice=self._current_solfeggio_value(),
            ambient_volume=round(self.ambient_volume_var.get()),
            close_to_tray=self.close_to_tray_var.get(),
            show_next_reminder=self.show_next_reminder_var.get(),
            global_hotkeys_enabled=self.global_hotkeys_var.get(),
            floating_status_enabled=self.floating_status_var.get(),
            migration_completed=True,
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
        self.audio.play_ambient(
            self.app_settings.ambient_choice,
            self.app_settings.solfeggio_choice,
            self.app_settings.ambient_volume / 100.0,
        )
        self.settings_frame.pack_forget()
        self.break_prompt_frame.pack_forget()
        self.running_frame.pack(fill="both", expand=True)
        self.pause_button.config(text="暂停")
        self.render_cache.invalidate()
        self._update_focus_display()
        self.logger.info(
            "Focus started: duration=%s mode=%s preset=%s",
            settings.focus_duration_sec,
            settings.algorithm_mode.value,
            settings.reminder_preset.value,
        )
        self._schedule_tick(self.session_generation)

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
                self.pause_button.config(text="继续")
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
        self.render_cache.update(
            "timer", timer_text, lambda value: self.timer_label.config(text=value)
        )
        phase = self.session.current_phase
        state_suffix = "（已暂停）" if self.session.state is SessionState.PAUSED else ""
        phase_text = f"{PHASE_NAMES[phase]}{state_suffix}"
        self.render_cache.update(
            "phase", phase_text, lambda value: self.phase_label.config(text=value)
        )
        interval = self._phase_interval(phase)
        interval_text = format_reminder_status(
            interval.minimum_sec,
            interval.maximum_sec,
            self.app_settings.show_next_reminder,
            self.session.next_reminder_remaining_sec,
        )
        self.render_cache.update(
            "interval", interval_text,
            lambda value: self.interval_label.config(text=value),
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
                self.pause_button.config(text="继续")
            elif self.session.state is SessionState.PAUSED:
                self.session.resume()
                self.pause_button.config(text="暂停")
            self._update_long_break_display()
            return
        if self.session.state is SessionState.FOCUSING:
            self.session.pause()
            self.audio.pause_ambient()
            self.pause_button.config(text="继续")
        elif self.session.state is SessionState.PAUSED:
            self.session.resume()
            self.audio.resume_ambient()
            self.pause_button.config(text="暂停")
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
        self.audio.stop_ambient()
        self.floating_status.end_session()
        self.running_frame.pack_forget()
        self.break_prompt_frame.pack(fill="both", expand=True)
        self.logger.info("Focus completed; waiting for long-break confirmation")

    def _start_long_break(self) -> None:
        if self.session is None:
            return
        try:
            duration = self._minutes(self.long_break_var.get(), "大休息")
        except ValueError as error:
            messagebox.showerror("输入错误", str(error))
            return
        self.session.start_long_break(duration)
        self.break_prompt_frame.pack_forget()
        self.running_frame.pack(fill="both", expand=True)
        self.pause_button.config(text="暂停")
        self.render_cache.invalidate()
        self._update_long_break_display()
        self._schedule_tick(self.session_generation)

    def _update_long_break_display(self) -> None:
        if self.session is None:
            return
        remaining = self.session.long_break_remaining_sec
        timer_text = self._format_seconds(remaining)
        phase_text = "大休息（已暂停）" if self.session.state is SessionState.PAUSED else "大休息"
        self.render_cache.update(
            "timer", timer_text, lambda value: self.timer_label.config(text=value)
        )
        self.render_cache.update(
            "phase", phase_text, lambda value: self.phase_label.config(text=value)
        )
        self.render_cache.update(
            "interval", "休息期间不会产生随机提醒",
            lambda value: self.interval_label.config(text=value),
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
        self.audio.stop_ambient()
        self.floating_status.end_session()
        self.running_frame.pack_forget()
        self.break_prompt_frame.pack_forget()
        self.settings_frame.pack(fill="both", expand=True)
        self.render_cache.invalidate()
        self.root.deiconify()

    def _show_reminder(self, phase: V2Phase | None) -> None:
        if self.session is None:
            return
        preset = self.session.settings.reminder_preset
        if not self.session.settings.break_countdown_enabled:
            self.tray.notify("CountdownApp", "微休息提醒：放松视线，确认当前任务。")
            self.audio.play_bell(self._current_audio_path())
            self._stop_audio_later(5)
            self.session.dismiss_reminder()
            return
        if phase is V2Phase.DEEP_FOCUS:
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
            self._show_banner("我还在原任务上吗？", duration)
            return
        self._show_overlay(self.session.settings.microbreak_duration_sec, preset)

    def _show_banner(self, message: str, duration_sec: int) -> None:
        self._close_reminder(dismiss=False)
        window = tk.Toplevel(self.root)
        self.reminder_window = window
        window.title("CountdownApp 提醒")
        window.attributes("-topmost", True)
        width, height = 460, 150
        x = max(0, (window.winfo_screenwidth() - width) // 2)
        window.geometry(f"{width}x{height}+{x}+40")
        body = ttk.Frame(window, padding=18)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text=message, font=("Microsoft YaHei UI", 16, "bold")).pack(pady=8)
        ttk.Button(body, text="跳过", command=self._close_reminder).pack()
        window.bind("<Escape>", lambda _event: self._close_reminder())
        window.protocol("WM_DELETE_WINDOW", self._close_reminder)
        self.reminder_after_id = self.root.after(
            duration_sec * 1000,
            lambda: self._close_reminder(completed_automatically=True),
        )
        self.audio.play_bell(self._current_audio_path())

    def _show_overlay(self, duration_sec: int, preset: ReminderPreset) -> None:
        self._close_reminder(dismiss=False)
        window = tk.Toplevel(self.root)
        self.reminder_window = window
        window.overrideredirect(True)
        window.attributes("-topmost", True)
        window.configure(bg="black")
        window.geometry(f"{window.winfo_screenwidth()}x{window.winfo_screenheight()}+0+0")
        if preset is ReminderPreset.BALANCED:
            window.attributes("-alpha", 0.82)
        label = tk.Label(
            window,
            text="",
            font=("Microsoft YaHei UI", 86, "bold"),
            fg="#62d995",
            bg="black",
        )
        label.pack(expand=True)
        button = tk.Button(
            window,
            text="跳过（Esc）",
            command=self._close_reminder,
            font=("Microsoft YaHei UI", 14),
        )
        button.pack(pady=30)
        window.bind("<Escape>", lambda _event: self._close_reminder())
        deadline = time.monotonic() + duration_sec
        overlay_cache = RenderCache()

        def update() -> None:
            if self.reminder_window is not window or not window.winfo_exists():
                return
            remaining = max(0, math.ceil(deadline - time.monotonic()))
            overlay_cache.update(
                "countdown",
                f"{remaining} 秒\n放松眼睛和肩膀",
                lambda value: label.config(text=value),
            )
            if time.monotonic() >= deadline:
                self._close_reminder(completed_automatically=True)
            else:
                self.reminder_after_id = self.root.after(self.OVERLAY_TICK_MS, update)

        update()
        self.audio.play_bell(self._current_audio_path())

    def _close_reminder(
        self,
        dismiss: bool = True,
        completed_automatically: bool = False,
    ) -> None:
        if self.reminder_after_id is not None:
            try:
                self.root.after_cancel(self.reminder_after_id)
            except tk.TclError:
                pass
            self.reminder_after_id = None
        if self.audio_after_id is not None:
            try:
                self.root.after_cancel(self.audio_after_id)
            except tk.TclError:
                pass
            self.audio_after_id = None
        window, self.reminder_window = self.reminder_window, None
        if window is not None:
            try:
                window.destroy()
            except tk.TclError:
                pass
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
                self.audio.stop_ambient()
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
        self.audio.close()
        self.hotkeys.stop()
        self.tray.stop()
        try:
            self.root.destroy()
        except tk.TclError:
            pass


def run() -> None:
    root = tk.Tk()
    CountdownApp(root)
    root.mainloop()
