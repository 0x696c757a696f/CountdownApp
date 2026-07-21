from __future__ import annotations

import logging
import queue
from pathlib import Path

from . import APP_NAME


class TrayService:
    """Tray adapter that communicates with Tk only through a command queue."""

    def __init__(
        self,
        icon_path: Path,
        commands: "queue.Queue[str]",
        logger: logging.Logger,
    ):
        self.icon_path = icon_path
        self.commands = commands
        self.logger = logger
        self.icon = None
        self._focus_active = False

    @property
    def available(self) -> bool:
        return self.icon is not None

    def is_floating_timer_action_visible(self, _item) -> bool:
        return self._focus_active

    def set_focus_active(self, active: bool) -> None:
        active = bool(active)
        if active == self._focus_active:
            return
        self._focus_active = active
        if self.icon is None:
            return
        try:
            self.icon.update_menu()
        except Exception as error:
            self.logger.warning("Updating tray menu failed: %s", error)

    def start(self) -> bool:
        try:
            from PIL import Image
            from pystray import Icon, Menu, MenuItem

            image = Image.open(self.icon_path)
            menu = Menu(
                MenuItem("打开主界面", lambda *_: self.commands.put("show"), default=True),
                MenuItem(
                    "显示悬浮计时",
                    lambda *_: self.commands.put("show_floating"),
                    visible=self.is_floating_timer_action_visible,
                ),
                MenuItem("暂停 / 继续", lambda *_: self.commands.put("pause")),
                MenuItem("停止当前周期", lambda *_: self.commands.put("stop")),
                MenuItem("退出程序", lambda *_: self.commands.put("quit")),
            )
            self.icon = Icon("CountdownApp", image, APP_NAME, menu)
            self.icon.run_detached()
            return True
        except Exception as error:
            self.logger.warning("Tray initialization failed: %s", error)
            self.icon = None
            return False

    def notify(self, title: str, message: str) -> bool:
        if self.icon is None:
            return False
        try:
            self.icon.notify(message, title)
            return True
        except Exception as error:
            self.logger.warning("Tray notification failed: %s", error)
            return False

    def stop(self) -> None:
        icon, self.icon = self.icon, None
        if icon is None:
            return
        try:
            icon.stop()
        except Exception as error:
            self.logger.warning("Stopping tray failed: %s", error)
