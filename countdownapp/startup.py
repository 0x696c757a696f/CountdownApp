from __future__ import annotations

import subprocess
import sys
import winreg
from enum import Enum
from pathlib import Path
from typing import Protocol


APP_RUN_NAME = "CountdownApp"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


class StartupMode(str, Enum):
    OFF = "off"
    VISIBLE = "visible"
    SILENT = "silent"


class RegistryStore(Protocol):
    def read(self, name: str) -> str | None: ...
    def write(self, name: str, value: str) -> None: ...
    def delete(self, name: str) -> None: ...


class WindowsRunRegistry:
    """Current-user Windows Run-key adapter; no administrator rights required."""

    def read(self, name: str) -> str | None:
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ
            ) as key:
                value, _kind = winreg.QueryValueEx(key, name)
                return str(value)
        except FileNotFoundError:
            return None

    def write(self, name: str, value: str) -> None:
        with winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)

    def delete(self, name: str) -> None:
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE
            ) as key:
                winreg.DeleteValue(key, name)
        except FileNotFoundError:
            pass


def build_startup_command(
    executable: str | Path,
    entrypoint: str | Path | None = None,
    *,
    silent: bool = True,
) -> str:
    arguments = [str(executable)]
    if entrypoint is not None:
        arguments.append(str(entrypoint))
    if silent:
        arguments.append("--startup")
    return subprocess.list2cmdline(arguments)


def current_startup_commands() -> tuple[str, str]:
    if getattr(sys, "frozen", False):
        return (
            build_startup_command(sys.executable, silent=False),
            build_startup_command(sys.executable, silent=True),
        )
    entrypoint = Path(__file__).resolve().parents[1] / "countdown_app.py"
    return (
        build_startup_command(sys.executable, entrypoint, silent=False),
        build_startup_command(sys.executable, entrypoint, silent=True),
    )


def current_startup_command() -> str:
    """Backward-compatible alias for the silent startup command."""
    return current_startup_commands()[1]


def should_start_hidden(arguments: list[str], *, tray_ready: bool) -> bool:
    return tray_ready and "--startup" in arguments[1:]


class StartupManager:
    def __init__(
        self,
        visible_command: str | None = None,
        silent_command: str | None = None,
        registry: RegistryStore | None = None,
    ) -> None:
        current_visible, current_silent = current_startup_commands()
        self.visible_command = visible_command or current_visible
        self.silent_command = silent_command or current_silent
        self.registry = registry or WindowsRunRegistry()

    def get_mode(self) -> StartupMode:
        command = self.registry.read(APP_RUN_NAME)
        if command is None:
            return StartupMode.OFF
        normalized = command.strip().casefold()
        if normalized == self.silent_command.strip().casefold():
            return StartupMode.SILENT
        if normalized == self.visible_command.strip().casefold():
            return StartupMode.VISIBLE
        return StartupMode.OFF

    def reconcile_mode(self) -> StartupMode:
        """Remove a Run-key entry that points at a previous installation."""
        command = self.registry.read(APP_RUN_NAME)
        if command is None:
            return StartupMode.OFF
        mode = self.get_mode()
        if mode is StartupMode.OFF:
            self.registry.delete(APP_RUN_NAME)
        return mode

    def set_mode(self, mode: StartupMode) -> None:
        if mode is StartupMode.OFF:
            self.registry.delete(APP_RUN_NAME)
        elif mode is StartupMode.VISIBLE:
            self.registry.write(APP_RUN_NAME, self.visible_command)
        else:
            self.registry.write(APP_RUN_NAME, self.silent_command)

    def is_enabled(self) -> bool:
        return self.get_mode() is not StartupMode.OFF

    def set_enabled(self, enabled: bool) -> None:
        self.set_mode(StartupMode.SILENT if enabled else StartupMode.OFF)
