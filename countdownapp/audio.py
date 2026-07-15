from __future__ import annotations

import logging
import winsound
from pathlib import Path
from typing import Callable, Protocol


def should_play_return_bell(
    *, countdown_enabled: bool, completed_automatically: bool
) -> bool:
    """Return whether a completed microbreak should announce focus resumption."""
    return countdown_enabled and completed_automatically


class AudioBackend(Protocol):
    def play(self, path: str | Path) -> None: ...
    def stop(self) -> None: ...
    def close(self) -> None: ...


class PygameAudioBackend:
    def __init__(self):
        import pygame

        self._pygame = pygame
        if not pygame.mixer.get_init():
            pygame.mixer.init()

    def play(self, path: str | Path) -> None:
        source = Path(path)
        if not source.is_file():
            raise FileNotFoundError(source)
        self._pygame.mixer.music.load(str(source))
        self._pygame.mixer.music.play()

    def stop(self) -> None:
        if self._pygame.mixer.get_init():
            self._pygame.mixer.music.stop()

    def close(self) -> None:
        if self._pygame.mixer.get_init():
            self._pygame.mixer.quit()


class AudioService:
    """Lazy audio playback with one device retry and a Windows fallback."""

    def __init__(
        self,
        backend_factory: Callable[[], AudioBackend] = PygameAudioBackend,
        fallback: Callable[[], None] | None = None,
        logger: logging.Logger | None = None,
    ):
        self._backend_factory = backend_factory
        self._fallback = fallback or self._system_fallback
        self._logger = logger or logging.getLogger(__name__)
        self._backend: AudioBackend | None = None

    def play(self, path: str | Path) -> None:
        for attempt in range(2):
            try:
                if self._backend is None:
                    self._backend = self._backend_factory()
                self._backend.play(path)
                return
            except Exception as error:
                self._logger.warning(
                    "Audio playback attempt %s failed: %s", attempt + 1, error
                )
                self._reset_backend()
        try:
            self._fallback()
            self._logger.info("Used Windows system audio fallback")
        except Exception as error:
            self._logger.error("System audio fallback failed: %s", error)

    def stop(self) -> None:
        if self._backend is None:
            return
        try:
            self._backend.stop()
        except Exception as error:
            self._logger.warning("Stopping audio failed: %s", error)

    def close(self) -> None:
        self.stop()
        self._reset_backend()

    def _reset_backend(self) -> None:
        backend, self._backend = self._backend, None
        if backend is None:
            return
        try:
            backend.close()
        except Exception as error:
            self._logger.warning("Closing audio backend failed: %s", error)

    @staticmethod
    def _system_fallback() -> None:
        winsound.MessageBeep(winsound.MB_ICONASTERISK)
