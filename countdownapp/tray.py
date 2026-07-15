from __future__ import annotations

import logging
import queue
from pathlib import Path


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

    @property
    def available(self) -> bool:
        return self.icon is not None

    def start(self) -> bool:
        try:
            from PIL import Image
            from pystray import Icon, Menu, MenuItem

            image = Image.open(self.icon_path)
            menu = Menu(
                MenuItem("打开主界面", lambda *_: self.commands.put("show"), default=True),
                MenuItem("暂停 / 继续", lambda *_: self.commands.put("pause")),
                MenuItem("停止当前周期", lambda *_: self.commands.put("stop")),
                MenuItem("退出程序", lambda *_: self.commands.put("quit")),
            )
            self.icon = Icon("CountdownApp", image, "CountdownApp", menu)
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
