from __future__ import annotations

import ctypes
import logging
import queue
import sys
from ctypes import wintypes
from typing import Protocol


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
    MOD_ALT = 0x0001
    MOD_SHIFT = 0x0004
    MOD_NOREPEAT = 0x4000
    VK_P = 0x50
    VK_O = 0x4F
    BINDINGS = (
        (PAUSE_ID, MOD_ALT | MOD_SHIFT | MOD_NOREPEAT, VK_P, "pause"),
        (WINDOW_ID, MOD_ALT | MOD_SHIFT | MOD_NOREPEAT, VK_O, "toggle_window"),
    )

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

    @property
    def is_active(self) -> bool:
        return bool(self._registered_ids)

    def start(self) -> bool:
        if self.is_active:
            return True
        try:
            backend = self._backend or Win32HotkeyBackend()
            self._backend = backend
            for hotkey_id, modifiers, virtual_key, _command in self.BINDINGS:
                if not backend.register(hotkey_id, modifiers, virtual_key):
                    self._rollback()
                    self.logger.warning("Global hotkey registration conflict: id=%s", hotkey_id)
                    return False
                self._registered_ids.append(hotkey_id)
            return True
        except Exception as error:
            self._rollback()
            self.logger.warning("Global hotkey initialization failed: %s", error)
            return False

    def poll(self) -> None:
        if not self.is_active or self._backend is None:
            return
        commands_by_id = {
            hotkey_id: command
            for hotkey_id, _modifiers, _virtual_key, command in self.BINDINGS
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
