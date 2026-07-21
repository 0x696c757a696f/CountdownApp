from __future__ import annotations

import math
import time
import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from tkinter import ttk

from . import APP_NAME
from .adaptive import AttentionFeedback
from .display import cover_virtual_desktop
from .domain import ReminderPreset
from .presentation import RenderCache


FLOW_FEEDBACK_LABEL = "正在心流，延后下次提醒"


def banner_action_columns(
    requested_widths: tuple[int, ...],
    available_width: int,
) -> int:
    """Choose a complete-row or wrapped button layout for the current screen."""
    if not requested_widths:
        return 1
    candidates = (len(requested_widths), 2, 1)
    for columns in dict.fromkeys(candidates):
        if columns > len(requested_widths):
            continue
        column_widths = [
            max(requested_widths[column::columns])
            for column in range(columns)
            if requested_widths[column::columns]
        ]
        if sum(column_widths) + 8 * len(column_widths) <= available_width:
            return columns
    return 1


class ReminderResultKind(str, Enum):
    SKIPPED = "skipped"
    COMPLETED = "completed"
    FEEDBACK = "feedback"


@dataclass(frozen=True)
class ReminderResult:
    kind: ReminderResultKind
    feedback: AttentionFeedback | None = None


class ReminderView:
    """Owns the complete lifecycle of one reminder window."""

    OVERLAY_TICK_MS = 200

    def __init__(
        self,
        root: tk.Misc,
        clock: Callable[[], float] = time.monotonic,
        apply_icon: Callable[[tk.Toplevel], None] | None = None,
    ):
        self._root = root
        self._clock = clock
        self._apply_icon = apply_icon
        self._window: tk.Toplevel | None = None
        self._after_id: str | None = None
        self._on_result: Callable[[ReminderResult], None] | None = None

    @property
    def is_open(self) -> bool:
        return self._window is not None

    def show_banner(
        self,
        message: str,
        duration_sec: int,
        adaptive: bool,
        on_result: Callable[[ReminderResult], None],
    ) -> None:
        self.close()
        self._on_result = on_result
        window = tk.Toplevel(self._root)
        self._window = window
        window.withdraw()
        if self._apply_icon is not None:
            self._apply_icon(window)
        window.title(f"{APP_NAME}提醒")
        window.attributes("-topmost", True)
        screen_width = window.winfo_screenwidth()
        screen_height = window.winfo_screenheight()

        body = ttk.Frame(window, padding=18)
        body.pack(fill="both", expand=True)
        ttk.Label(
            body,
            text=message,
            font=("Microsoft YaHei UI", 16, "bold"),
            wraplength=max(1, round(screen_width * 0.86)),
            justify="center",
        ).pack(pady=8)
        actions = ttk.Frame(body)
        actions.pack(fill="x", pady=5)
        buttons: list[ttk.Button] = []
        if adaptive:
            for text, feedback in (
                ("仍在任务", AttentionFeedback.ON_TASK),
                ("刚才走神", AttentionFeedback.DISTRACTED),
                (FLOW_FEEDBACK_LABEL, AttentionFeedback.FLOW),
            ):
                buttons.append(
                    ttk.Button(
                        actions,
                        text=text,
                        width=max(10, len(text) * 2 + 2),
                        command=lambda value=feedback: self._finish(
                            ReminderResult(ReminderResultKind.FEEDBACK, value)
                        ),
                    )
                )
        buttons.append(
            ttk.Button(
                actions,
                text="跳过",
                width=8,
                command=lambda: self._finish(
                    ReminderResult(ReminderResultKind.SKIPPED)
                ),
            )
        )
        window.update_idletasks()
        columns = banner_action_columns(
            tuple(button.winfo_reqwidth() for button in buttons),
            available_width=max(1, round(screen_width * 0.92)),
        )
        for column in range(columns):
            actions.columnconfigure(column, weight=1)
        for index, button in enumerate(buttons):
            button.grid(
                row=index // columns,
                column=index % columns,
                sticky="ew",
                padx=4,
                pady=3,
            )
        window.update_idletasks()
        requested_width = body.winfo_reqwidth()
        requested_height = body.winfo_reqheight()
        x = max(0, (screen_width - requested_width) // 2)
        y = max(0, min(round(screen_height * 0.04), screen_height - requested_height))
        window.geometry(f"+{x}+{y}")
        window.deiconify()
        self._bind_close_actions(window)
        self._after_id = self._root.after(
            duration_sec * 1000,
            lambda: self._finish(ReminderResult(ReminderResultKind.COMPLETED)),
        )

    def show_overlay(
        self,
        duration_sec: int,
        preset: ReminderPreset,
        adaptive: bool,
        on_result: Callable[[ReminderResult], None],
    ) -> None:
        self.close()
        self._on_result = on_result
        window = tk.Toplevel(self._root)
        self._window = window
        window.withdraw()
        if self._apply_icon is not None:
            self._apply_icon(window)
        window.overrideredirect(True)
        window.attributes("-topmost", True)
        window.configure(bg="black")
        cover_virtual_desktop(window)
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
        actions = tk.Frame(window, bg="black")
        actions.pack(pady=30)
        if adaptive:
            for text, feedback in (
                ("仍在任务", AttentionFeedback.ON_TASK),
                ("刚才走神", AttentionFeedback.DISTRACTED),
                (FLOW_FEEDBACK_LABEL, AttentionFeedback.FLOW),
            ):
                tk.Button(
                    actions,
                    text=text,
                    command=lambda value=feedback: self._finish(
                        ReminderResult(ReminderResultKind.FEEDBACK, value)
                    ),
                    font=("Microsoft YaHei UI", 14),
                ).pack(side="left", padx=6)
        tk.Button(
            actions,
            text="跳过（Esc）",
            command=lambda: self._finish(ReminderResult(ReminderResultKind.SKIPPED)),
            font=("Microsoft YaHei UI", 14),
        ).pack(side="left", padx=6)
        self._bind_close_actions(window)
        window.deiconify()
        window.lift()
        if preset is ReminderPreset.STRONG:
            window.focus_force()
        else:
            window.focus_set()

        deadline = self._clock() + duration_sec
        cache = RenderCache()

        def update() -> None:
            if self._window is not window or not window.winfo_exists():
                return
            remaining = max(0, math.ceil(deadline - self._clock()))
            cache.update(
                "countdown",
                f"{remaining} 秒\n放松眼睛和肩膀",
                lambda value: label.config(text=value),
            )
            if self._clock() >= deadline:
                self._finish(ReminderResult(ReminderResultKind.COMPLETED))
            else:
                self._after_id = self._root.after(self.OVERLAY_TICK_MS, update)

        update()

    def close(self) -> None:
        if self._after_id is not None:
            try:
                self._root.after_cancel(self._after_id)
            except tk.TclError:
                pass
            self._after_id = None
        window, self._window = self._window, None
        self._on_result = None
        if window is not None:
            try:
                window.destroy()
            except tk.TclError:
                pass

    def _bind_close_actions(self, window: tk.Toplevel) -> None:
        skipped = lambda: self._finish(ReminderResult(ReminderResultKind.SKIPPED))
        window.bind("<Escape>", lambda _event: skipped())
        window.protocol("WM_DELETE_WINDOW", skipped)

    def _finish(self, result: ReminderResult) -> None:
        callback = self._on_result
        self.close()
        if callback is not None:
            callback(result)
