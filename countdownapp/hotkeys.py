from __future__ import annotations

import ctypes
import logging
import queue
import sys
from ctypes import wintypes
from dataclasses import dataclass
from typing import Protocol


MOD_ALT = 0x0001
MOD_CTRL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000


@dataclass(frozen=True)
class ParsedHotkey:
    display: str
    modifiers: int
    virtual_key: int


def parse_hotkey(shortcut: str) -> ParsedHotkey:
    modifier_values = {
        "CTRL": ("Ctrl", MOD_CTRL),
        "CONTROL": ("Ctrl", MOD_CTRL),
        "ALT": ("Alt", MOD_ALT),
        "SHIFT": ("Shift", MOD_SHIFT),
        "WIN": ("Win", MOD_WIN),
        "WINDOWS": ("Win", MOD_WIN),
    }
    parts = [part.strip() for part in shortcut.split("+") if part.strip()]
    modifiers = 0
    selected_modifiers: set[str] = set()
    key_parts: list[str] = []
    for part in parts:
        normalized = part.upper()
        modifier = modifier_values.get(normalized)
        if modifier is None:
            key_parts.append(normalized)
            continue
        display, value = modifier
        if display in selected_modifiers:
            raise ValueError(f"Duplicate modifier: {display}")
        selected_modifiers.add(display)
        modifiers |= value

    if modifiers == 0:
        raise ValueError("A modifier key is required")
    if len(key_parts) != 1:
        raise ValueError("A shortcut must contain exactly one non-modifier key")
    key = key_parts[0]
    if len(key) == 1 and ("A" <= key <= "Z" or "0" <= key <= "9"):
        virtual_key = ord(key)
        display_key = key
    elif key.startswith("F") and key[1:].isdigit() and 1 <= int(key[1:]) <= 12:
        virtual_key = 0x70 + int(key[1:]) - 1
        display_key = key
    elif key == "SPACE":
        virtual_key = 0x20
        display_key = "Space"
    else:
        raise ValueError(f"Unsupported hotkey: {key}")

    ordered_names = [
        name for name in ("Ctrl", "Alt", "Shift", "Win") if name in selected_modifiers
    ]
    return ParsedHotkey(
        "+".join((*ordered_names, display_key)),
        modifiers | MOD_NOREPEAT,
        virtual_key,
    )


class HotkeyBackend(Protocol):
    def register(self, hotkey_id: int, modifiers: int, virtual_key: int) -> bool: ...

    def unregister(self, hotkey_id: int) -> None: ...

    def poll(self) -> list[int]: ...


class Win32HotkeyBackend:
    WM_HOTKEY = 0x0312
    PM_REMOVE = 0x0001

    def __init__(self) -> None:
        if sys.platform != "win32":
            raise OSError("Global hotkeys are only available on Windows")
        self._user32 = ctypes.WinDLL("user32", use_last_error=True)
        self._user32.RegisterHotKey.argtypes = (
            wintypes.HWND,
            ctypes.c_int,
            wintypes.UINT,
            wintypes.UINT,
        )
        self._user32.RegisterHotKey.restype = wintypes.BOOL
        self._user32.UnregisterHotKey.argtypes = (wintypes.HWND, ctypes.c_int)
        self._user32.UnregisterHotKey.restype = wintypes.BOOL
        self._user32.PeekMessageW.argtypes = (
            ctypes.POINTER(wintypes.MSG),
            wintypes.HWND,
            wintypes.UINT,
            wintypes.UINT,
            wintypes.UINT,
        )
        self._user32.PeekMessageW.restype = wintypes.BOOL

    def register(self, hotkey_id: int, modifiers: int, virtual_key: int) -> bool:
        return bool(self._user32.RegisterHotKey(None, hotkey_id, modifiers, virtual_key))

    def unregister(self, hotkey_id: int) -> None:
        self._user32.UnregisterHotKey(None, hotkey_id)

    def poll(self) -> list[int]:
        messages: list[int] = []
        message = wintypes.MSG()
        while self._user32.PeekMessageW(
            ctypes.byref(message),
            None,
            self.WM_HOTKEY,
            self.WM_HOTKEY,
            self.PM_REMOVE,
        ):
            messages.append(int(message.wParam))
        return messages


class GlobalHotkeyService:
    """Publishes native hotkey messages into the existing GUI command queue."""

    PAUSE_ID = 0x4CA1
    WINDOW_ID = 0x4CA2
    DEFAULT_PAUSE = "Alt+Shift+P"
    DEFAULT_WINDOW = "Alt+Shift+O"

    def __init__(
        self,
        commands: "queue.Queue[str]",
        logger: logging.Logger,
        backend: HotkeyBackend | None = None,
    ) -> None:
        self.commands = commands
        self.logger = logger
        self._backend = backend
        self._registered_ids: list[int] = []
        self._bindings: tuple[tuple[int, ParsedHotkey, str], ...] = ()
        self.last_error = ""

    @property
    def is_active(self) -> bool:
        return bool(self._registered_ids)

    def start(
        self,
        pause_shortcut: str = DEFAULT_PAUSE,
        window_shortcut: str = DEFAULT_WINDOW,
    ) -> bool:
        if self.is_active:
            return True
        self.last_error = ""
        try:
            pause = parse_hotkey(pause_shortcut)
            window = parse_hotkey(window_shortcut)
            if pause.display == window.display:
                self.last_error = "Pause and window shortcuts must be different"
                return False
            self._bindings = (
                (self.PAUSE_ID, pause, "pause"),
                (self.WINDOW_ID, window, "toggle_window"),
            )
            backend = self._backend or Win32HotkeyBackend()
            self._backend = backend
            for hotkey_id, parsed, _command in self._bindings:
                if not backend.register(
                    hotkey_id, parsed.modifiers, parsed.virtual_key
                ):
                    self._rollback()
                    self.last_error = f"Shortcut already in use: {parsed.display}"
                    self.logger.warning(
                        "Global hotkey registration conflict: id=%s", hotkey_id
                    )
                    return False
                self._registered_ids.append(hotkey_id)
            return True
        except ValueError as error:
            self.last_error = str(error)
            self.logger.warning("Invalid global hotkey setting: %s", error)
            return False
        except Exception as error:
            self._rollback()
            self.last_error = str(error)
            self.logger.warning("Global hotkey initialization failed: %s", error)
            return False

    def poll(self) -> None:
        if not self.is_active or self._backend is None:
            return
        commands_by_id = {
            hotkey_id: command
            for hotkey_id, _parsed, command in self._bindings
        }
        try:
            for hotkey_id in self._backend.poll():
                command = commands_by_id.get(hotkey_id)
                if command is not None:
                    self.commands.put(command)
        except Exception as error:
            self.logger.warning("Polling global hotkeys failed: %s", error)

    def stop(self) -> None:
        self._rollback()

    def _rollback(self) -> None:
        if self._backend is not None:
            for hotkey_id in self._registered_ids:
                try:
                    self._backend.unregister(hotkey_id)
                except Exception as error:
                    self.logger.warning("Unregistering global hotkey failed: %s", error)
        self._registered_ids.clear()
