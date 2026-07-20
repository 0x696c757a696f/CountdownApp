from __future__ import annotations

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
from .app_icon import apply_window_icon, configure_process_identity
from .audio import AudioEngine, should_play_return_bell
from .break_prompt_view import BreakPromptBindings, BreakPromptView
from .config import AppSettings, ConfigStore
from .domain import (
    ReminderPreset,
    SessionSettings,
    SessionState,
    V2Phase,
    reminder_coverage_warnings,
)
from .floating import FloatingStatusController, TkFloatingStatusView
from .focus_coordinator import FocusCoordinator
from .hotkeys import GlobalHotkeyService
from .logging_config import configure_logging
from .presentation import (
    format_ambient_summary,
    responsive_window_layout,
)
from .resources import install_dir, resource_path
from .reminder_view import (
    ReminderResult,
    ReminderResultKind,
    ReminderView,
)
from .runtime_view import RuntimeBindings, RuntimeDisplay, RuntimeView
from .session import RuntimeEventKind
from .settings_form import (
    AMBIENT_TEXTURE_OPTIONS,
    NOISE_OPTIONS,
    SOLFEGGIO_OPTIONS,
    SettingsForm,
)
from .settings_view import SettingsView, SettingsViewBindings
from .single_instance import SingleInstanceGuard, show_native_message
from .startup import StartupManager, StartupMode, should_start_hidden
from .tray import TrayService
from .v2_settings_dialog import V2SettingsDialog


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
        self.app_icon = None
        try:
            self.app_icon = apply_window_icon(self.root)
        except (OSError, tk.TclError) as error:
            self.logger.warning("Applying application icon failed: %s", error)
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
        self.focus = FocusCoordinator(SystemRandom(), time.monotonic)
        self.tick_after_id: str | None = None
        self.tray_after_id: str | None = None
        self.audio_after_id: str | None = None
        self.reminder_view = ReminderView(self.root)
        self.tray_commands: "queue.Queue[str]" = queue.Queue()
        self.tray = TrayService(
            resource_path("clock_icon.png"), self.tray_commands, self.logger
        )
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

    def _build_ui(self) -> None:
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
        self.ambient_texture_var = self.settings_form.ambient_texture
        self.solfeggio_var = self.settings_form.solfeggio
        self.ambient_volume_var = self.settings_form.ambient_volume
        self.ambient_volume_label_var = self.settings_form.ambient_volume_label
        self.close_to_tray_var = self.settings_form.close_to_tray
        self.show_next_reminder_var = self.settings_form.show_next_reminder
        self.global_hotkeys_var = self.settings_form.global_hotkeys
        self.floating_status_var = self.settings_form.floating_status
        self.pause_hotkey_var = self.settings_form.pause_hotkey
        self.window_hotkey_var = self.settings_form.window_hotkey

        self.settings_view = SettingsView(
            self.root,
            self.settings_form,
            SettingsViewBindings(
                on_open_v2=self._open_v2_settings,
                on_test_audio=self._test_audio,
                on_choose_audio=self._choose_audio,
                on_preview_ambient=self._preview_ambient,
                on_stop_ambient=self._stop_ambient_playback,
                on_ambient_volume_change=self._on_ambient_volume_changed,
                on_floating_status_change=self._on_floating_status_changed,
                on_global_hotkeys_change=self._on_global_hotkeys_changed,
                on_close_to_tray_change=self._on_close_to_tray_changed,
                on_startup_change=self._on_startup_changed,
                on_start_focus=self._start_focus,
                on_shutdown=self._shutdown,
            ),
        )
        self.v2_dialog = V2SettingsDialog(
            self.root,
            self.settings_form,
            on_reset=self.settings_view.reset_v2_defaults,
            on_closed=self.settings_view.refresh_algorithm,
        )
        self.settings_view.show()

        self.runtime_view = RuntimeView(
            self.root,
            RuntimeBindings(
                noise_var=self.ambient_var,
                texture_var=self.ambient_texture_var,
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
            texture_options=tuple(AMBIENT_TEXTURE_OPTIONS),
            tone_options=tuple(SOLFEGGIO_OPTIONS),
        )

        self.break_prompt_view = BreakPromptView(
            self.root,
            BreakPromptBindings(
                duration_var=self.long_break_var,
                on_start=self._start_long_break,
                on_skip=self._skip_long_break,
                on_shutdown=self._shutdown,
            ),
        )

    def _load_form(self, settings: AppSettings) -> None:
        self.settings_form.load(settings)
        self._refresh_hotkey_controls()
        self.settings_view.set_startup_mode(self.startup_mode)
        self.settings_view.refresh_algorithm()
        self._refresh_runtime_ambient_summary()

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
        self.settings_view.refresh_hotkey_controls()

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
        requested = self.settings_view.startup_mode
        previous = self.startup_mode
        try:
            self.startup_manager.set_mode(requested)
        except OSError as error:
            self.logger.error("Updating Windows startup setting failed: %s", error)
            self.settings_view.set_startup_mode(previous)
            messagebox.showerror("开机启动设置失败", str(error))
            return
        self.startup_mode = requested

    def _open_v2_settings(self) -> None:
        self.v2_dialog.show()

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
        sources: tuple[str, ...],
        volume: float,
        on_complete: Callable[[bool], None] | None = None,
    ) -> None:
        if not sources:
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

        self.ambient_tasks.request(sources, volume, completed)

    def _preview_ambient(self) -> None:
        self._play_ambient_selection(
            self.settings_form.ambient_sources,
            self.settings_form.ambient_volume_fraction,
        )

    def _apply_runtime_ambient(self) -> None:
        sources = self.settings_form.ambient_sources
        volume = min(100, max(0, round(self.ambient_volume_var.get())))
        self._save_runtime_ambient_preferences()
        if sources:
            self.runtime_view.set_ambient_summary("正在准备背景音…")
        self._play_ambient_selection(
            sources,
            volume / 100.0,
            lambda played: self._runtime_ambient_completed(
                sources, volume, played
            ),
        )

    def _runtime_ambient_completed(
        self, sources: tuple[str, ...], volume: int, played: bool
    ) -> None:
        if played and self.focus.state is SessionState.PAUSED:
            self.audio.pause_ambient()
        if not played:
            self.runtime_view.set_ambient_summary(
                "播放失败 · 已保留选择，等待下次重试"
            )
        else:
            self.runtime_view.set_ambient_summary(
                format_ambient_summary(sources, volume)
            )

    def _stop_ambient_playback(self) -> None:
        self.ambient_tasks.cancel()
        self.audio.stop_ambient()

    def _save_runtime_ambient_preferences(self) -> None:
        noise = self.settings_form.ambient_value
        texture = self.settings_form.ambient_texture_value
        tone = self.settings_form.solfeggio_value
        volume = min(100, max(0, round(self.ambient_volume_var.get())))

        updated = replace(
            self.app_settings,
            ambient_choice=noise,
            ambient_texture_choice=texture,
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
            format_ambient_summary(self.settings_form.ambient_sources, volume)
        )

    def _on_runtime_ambient_volume_changed(self, value: str) -> None:
        volume = min(100, max(0, round(float(value))))
        self.ambient_volume_label_var.set(f"{volume}%")
        self.ambient_tasks.set_volume(volume / 100.0)
        self.audio.set_ambient_volume(volume / 100.0)
        self.runtime_view.set_ambient_summary(
            format_ambient_summary(
                self.settings_form.ambient_sources,
                volume,
            )
        )

    def _stop_runtime_ambient(self) -> None:
        self.ambient_var.set("关闭")
        self.ambient_texture_var.set("关闭")
        self.solfeggio_var.set("关闭")
        self._apply_runtime_ambient()

    def _toggle_runtime_ambient_controls(self) -> None:
        self.runtime_view.toggle_ambient_controls()

    def _apply_runtime_window_layout(self) -> None:
        self.runtime_view.apply_window_layout()

    def _refresh_runtime_ambient_summary(self) -> None:
        self.runtime_view.set_ambient_summary(
            format_ambient_summary(
                self.settings_form.ambient_sources,
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
            self.settings_view.set_error(str(error))
            return
        if not self._confirm_reminder_coverage(settings):
            return
        self.settings_view.set_error("")
        self.app_settings = self.settings_form.build_app_settings(
            self.app_settings, settings
        )
        try:
            self.store.save(self.app_settings)
        except OSError as error:
            self.logger.error("Saving settings failed: %s", error)
            messagebox.showwarning("配置未保存", "本次可以继续运行，但设置未能保存。")

        generation = self.focus.start(
            settings,
            show_next_reminder=self.app_settings.show_next_reminder,
        )
        self.floating_status.set_enabled(self.app_settings.floating_status_enabled)
        self.floating_status.begin_session()
        self._play_ambient_selection(
            tuple(
                source
                for source in (
                    self.app_settings.ambient_choice,
                    self.app_settings.ambient_texture_choice,
                    self.app_settings.solfeggio_choice,
                )
                if source != "off"
            ),
            self.app_settings.ambient_volume / 100.0,
        )
        self.settings_view.hide()
        self.break_prompt_view.hide()
        ambient_summary = format_ambient_summary(
            self.settings_form.ambient_sources,
            round(self.ambient_volume_var.get()),
        )
        self.runtime_view.show_focus(ambient_summary)
        self.runtime_view.invalidate()
        self._render_focus_display(self.focus.display)
        self.logger.info(
            "Focus started: duration=%s mode=%s preset=%s",
            settings.focus_duration_sec,
            settings.algorithm_mode.value,
            settings.reminder_preset.value,
        )
        self._schedule_tick(generation)

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
        update = self.focus.tick(generation)
        if update is None:
            return
        for event in update.events:
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
        if update.display is not None:
            if update.long_break:
                self.runtime_view.render(update.display)
            else:
                self._render_focus_display(update.display)
        if update.should_continue:
            self._schedule_tick(generation)

    def _render_focus_display(self, display: RuntimeDisplay) -> None:
        self.runtime_view.render(display)
        self.floating_status.update(display.timer, display.phase)

    def _toggle_pause(self) -> None:
        transition = self.focus.toggle_pause()
        if transition is None:
            return
        self.runtime_view.set_pause_state(
            paused=transition.paused,
            long_break=transition.long_break,
        )
        if transition.long_break:
            self.runtime_view.render(transition.display)
            return
        if transition.paused:
            if transition.reminder_was_visible:
                self._close_reminder(dismiss=False)
            self.audio.pause_ambient()
        else:
            self.audio.resume_ambient()
        self._render_focus_display(transition.display)

    def _stop_focus(self) -> None:
        if not self.focus.is_active:
            return
        if not messagebox.askyesno("停止当前周期", "确定停止并返回设置界面吗？"):
            return
        self.logger.info("Session stopped by user")
        self._return_to_settings()

    def _show_break_prompt(self) -> None:
        self._close_reminder(dismiss=False)
        self.audio.stop_bell()
        self._stop_ambient_playback()
        self.floating_status.end_session()
        self.runtime_view.hide()
        self.break_prompt_view.show()
        self.logger.info("Focus completed; waiting for long-break confirmation")

    def _start_long_break(self) -> None:
        if self.focus.state is not SessionState.BREAK_PROMPT:
            return
        try:
            duration = SettingsForm.parse_minutes(
                self.long_break_var.get(), "大休息"
            )
        except ValueError as error:
            messagebox.showerror("输入错误", str(error))
            return
        display = self.focus.start_long_break(duration)
        self.break_prompt_view.hide()
        self.runtime_view.show_long_break()
        self.runtime_view.invalidate()
        self.runtime_view.render(display)
        self._schedule_tick(generation=self.focus.generation)

    def _skip_long_break(self) -> None:
        self._return_to_settings()

    def _return_to_settings(self) -> None:
        self.focus.stop()
        if self.tick_after_id is not None:
            self.root.after_cancel(self.tick_after_id)
            self.tick_after_id = None
        self._close_reminder(dismiss=False)
        self.audio.stop_bell()
        self._stop_ambient_playback()
        self.floating_status.end_session()
        self.runtime_view.hide()
        self.break_prompt_view.hide()
        self.settings_view.show()
        self.runtime_view.invalidate()
        self.root.deiconify()

    def _show_reminder(self, phase: V2Phase | None) -> None:
        settings = self.focus.settings
        if settings is None:
            return
        preset = settings.reminder_preset
        adaptive = settings.adaptive_reminders_enabled
        self.logger.info(
            "Reminder triggered: phase=%s preset=%s adaptive=%s",
            phase.value if phase is not None else "classic",
            preset.value,
            adaptive,
        )
        if not settings.break_countdown_enabled:
            if adaptive:
                self._show_banner("我还在原任务上吗？", 8)
                return
            self.tray.notify("CountdownApp", "微休息提醒：放松视线，确认当前任务。")
            self.audio.play_bell(self._current_audio_path())
            self._stop_audio_later(5)
            self.focus.dismiss_reminder()
            return
        if phase is V2Phase.DEEP_FOCUS:
            if adaptive:
                self._show_banner("深度专注：放松视线，确认任务方向。", 8)
                return
            notified = self.tray.notify("CountdownApp", "深度专注提醒：放松视线，确认任务方向。")
            self.audio.play_bell(self._current_audio_path())
            self._stop_audio_later(5)
            if notified:
                self.focus.dismiss_reminder()
            else:
                self._show_banner("深度专注：放松视线，确认任务方向。", 5)
            return
        if phase is V2Phase.ATTENTION_ANCHOR:
            duration = (
                5
                if preset is ReminderPreset.BALANCED
                else settings.microbreak_duration_sec
            )
            if adaptive:
                duration = max(8, duration)
            self._show_banner("我还在原任务上吗？", duration)
            return
        self._show_overlay(settings.microbreak_duration_sec, preset)

    def _show_banner(self, message: str, duration_sec: int) -> None:
        settings = self.focus.settings
        adaptive = bool(settings and settings.adaptive_reminders_enabled)
        self.reminder_view.show_banner(
            message,
            duration_sec,
            adaptive,
            self._handle_reminder_result,
        )
        self.audio.play_bell(self._current_audio_path())

    def _show_overlay(self, duration_sec: int, preset: ReminderPreset) -> None:
        settings = self.focus.settings
        adaptive = bool(settings and settings.adaptive_reminders_enabled)
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
        if not self.focus.record_feedback(feedback):
            return
        self.logger.info("Attention feedback recorded: %s", feedback.value)
        self._close_reminder(dismiss=False)
        self._render_focus_display(self.focus.display)

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
        if dismiss:
            self.focus.dismiss_reminder()
        settings = self.focus.settings
        countdown_enabled = bool(settings and settings.break_countdown_enabled)
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
            if self.focus.state is SessionState.IDLE:
                self._stop_ambient_playback()
            self.root.withdraw()
        else:
            messagebox.showwarning("托盘不可用", "系统托盘初始化失败，窗口不能隐藏。")

    def _on_window_close(self) -> None:
        active = self.focus.is_active
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
                    if self.focus.state is SessionState.IDLE or messagebox.askyesno(
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
        self.focus.shutdown()
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
        try:
            configure_process_identity()
        except OSError as error:
            logger.warning("Setting Windows application identity failed: %s", error)
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
