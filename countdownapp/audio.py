from __future__ import annotations

import logging
import math
import secrets
import winsound
from array import array
from pathlib import Path
from typing import Callable, Protocol

from .ambient_library import PreparedAmbient, prepare_ambient


def should_play_return_bell(
    *, countdown_enabled: bool, completed_automatically: bool
) -> bool:
    """Return whether a completed microbreak should announce focus resumption."""
    return countdown_enabled and completed_automatically


class UnifiedAudioBackend(Protocol):
    def play_bell(self, path: str | Path) -> None: ...
    def stop_bell(self) -> None: ...
    def play_ambient(self, sources: tuple[str, ...], volume: float) -> None: ...
    def play_prepared_ambient(
        self, prepared: PreparedAmbient, volume: float
    ) -> None: ...
    def set_ambient_volume(self, volume: float) -> None: ...
    def pause_ambient(self) -> None: ...
    def resume_ambient(self) -> None: ...
    def stop_ambient(self) -> None: ...
    def close(self) -> None: ...


class AudioEngine:
    """Coordinates reminder bells and ambient audio behind one device owner."""

    def __init__(
        self,
        backend_factory: Callable[[], UnifiedAudioBackend] | None = None,
        *,
        ducking_ratio: float = 0.35,
        fallback: Callable[[], None] | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._backend_factory = backend_factory or PygameUnifiedAudioBackend
        self._backend: UnifiedAudioBackend | None = None
        self._ducking_ratio = min(1.0, max(0.0, ducking_ratio))
        self._fallback = fallback or self._system_fallback
        self._logger = logger or logging.getLogger(__name__)
        self._ambient_sources: tuple[str, ...] = ()
        self._ambient_volume = 0.0
        self._ambient_paused = False
        self._bell_active = False

    def play_ambient(self, sources: tuple[str, ...], volume: float) -> bool:
        sources = tuple(source for source in sources if source != "off")
        if not sources:
            self.stop_ambient()
            return True
        self._ambient_sources = sources
        self._ambient_volume = min(1.0, max(0.0, float(volume)))
        self._ambient_paused = False
        for attempt in range(2):
            try:
                self._get_backend().play_ambient(sources, self._ambient_volume)
                return True
            except Exception as error:
                self._logger.warning(
                    "Ambient playback attempt %s failed: %s", attempt + 1, error
                )
                self._reset_backend()
        self._ambient_sources = ()
        return False

    def play_prepared_ambient(
        self, prepared: PreparedAmbient, volume: float
    ) -> bool:
        if not prepared.sources:
            self.stop_ambient()
            return True
        self._ambient_sources = prepared.sources
        self._ambient_volume = min(1.0, max(0.0, float(volume)))
        self._ambient_paused = False
        for attempt in range(2):
            try:
                self._get_backend().play_prepared_ambient(
                    prepared, self._ambient_volume
                )
                return True
            except Exception as error:
                self._logger.warning(
                    "Prepared ambient playback attempt %s failed: %s",
                    attempt + 1,
                    error,
                )
                self._reset_backend()
        self._ambient_sources = ()
        return False

    def play_bell(self, path: str | Path) -> bool:
        self._bell_active = False
        for attempt in range(2):
            try:
                backend = self._get_backend()
                if attempt and self._ambient_sources:
                    backend.play_ambient(
                        self._ambient_sources, self._ambient_volume
                    )
                if self._ambient_sources:
                    backend.set_ambient_volume(
                        self._ambient_volume * self._ducking_ratio
                    )
                backend.play_bell(path)
                self._bell_active = True
                return True
            except Exception as error:
                self._logger.warning(
                    "Audio playback attempt %s failed: %s", attempt + 1, error
                )
                self._reset_backend()
        try:
            self._fallback()
        except Exception as error:
            self._logger.error("System audio fallback failed: %s", error)
        self._restore_ambient()
        return False

    def stop_bell(self) -> None:
        self._bell_active = False
        if self._backend is None:
            return
        backend = self._backend
        try:
            backend.stop_bell()
            if self._ambient_sources:
                backend.set_ambient_volume(self._ambient_volume)
        except Exception as error:
            self._logger.warning("Stopping bell audio failed: %s", error)
            self._reset_backend()
            self._restore_ambient()

    def set_ambient_volume(self, volume: float) -> None:
        self._ambient_volume = min(1.0, max(0.0, float(volume)))
        if self._backend is not None and self._ambient_sources:
            effective = (
                self._ambient_volume * self._ducking_ratio
                if self._bell_active
                else self._ambient_volume
            )
            try:
                self._backend.set_ambient_volume(effective)
            except Exception as error:
                self._logger.warning("Changing ambient volume failed: %s", error)
                self._bell_active = False
                self._reset_backend()
                self._restore_ambient()

    def pause_ambient(self) -> None:
        self._ambient_paused = True
        if self._backend is not None and self._ambient_sources:
            try:
                self._backend.pause_ambient()
            except Exception as error:
                self._logger.warning("Pausing ambient audio failed: %s", error)
                self._bell_active = False
                self._reset_backend()
                self._restore_ambient()

    def resume_ambient(self) -> None:
        self._ambient_paused = False
        if not self._ambient_sources:
            return
        if self._backend is None:
            self._restore_ambient()
            return
        try:
            self._backend.resume_ambient()
        except Exception as error:
            self._logger.warning("Resuming ambient audio failed: %s", error)
            self._bell_active = False
            self._reset_backend()
            self._restore_ambient()

    def stop_ambient(self) -> None:
        if self._backend is not None and self._ambient_sources:
            try:
                self._backend.stop_ambient()
            except Exception as error:
                self._logger.warning("Stopping ambient audio failed: %s", error)
                self._reset_backend()
        self._ambient_sources = ()
        self._ambient_paused = False

    def close(self) -> None:
        self._ambient_sources = ()
        self._ambient_paused = False
        self._bell_active = False
        self._reset_backend()

    def _get_backend(self) -> UnifiedAudioBackend:
        if self._backend is None:
            self._backend = self._backend_factory()
        return self._backend

    def _reset_backend(self) -> None:
        backend, self._backend = self._backend, None
        if backend is not None:
            try:
                backend.close()
            except Exception as error:
                self._logger.warning("Closing audio backend failed: %s", error)

    def _restore_ambient(self) -> None:
        if not self._ambient_sources:
            return
        try:
            self._get_backend().play_ambient(
                self._ambient_sources, self._ambient_volume
            )
            if self._ambient_paused:
                self._backend.pause_ambient()
        except Exception as error:
            self._logger.warning("Restoring ambient audio failed: %s", error)
            self._reset_backend()

    @staticmethod
    def _system_fallback() -> None:
        winsound.MessageBeep(winsound.MB_ICONASTERISK)


class PygameUnifiedAudioBackend:
    """Owns pygame's global mixer and keeps bells on a channel separate from ambience."""

    def __init__(self, pygame_module=None) -> None:
        if pygame_module is None:
            import pygame
        else:
            pygame = pygame_module

        self._pygame = pygame
        if not pygame.mixer.get_init():
            pygame.mixer.init(frequency=44_100, size=-16, channels=2)
        self._ambient_sounds: list[object] = []
        self._ambient_channels: list[object] = []
        self._ambient_sources: tuple[str, ...] = ()
        self._ambient_volume = 0.2
        self._ambient_cache: dict[tuple[object, ...], object] = {}

    def play_bell(self, path: str | Path) -> None:
        source = Path(path)
        if not source.is_file():
            raise FileNotFoundError(source)
        self._pygame.mixer.music.load(str(source))
        self._pygame.mixer.music.play()

    def stop_bell(self) -> None:
        if self._pygame.mixer.get_init():
            self._pygame.mixer.music.stop()

    def play_ambient(self, sources: tuple[str, ...], volume: float) -> None:
        mixer_settings = self._pygame.mixer.get_init()
        if mixer_settings is None:
            raise RuntimeError("Audio mixer is not initialized")
        sample_rate, _sample_format, _channels = mixer_settings
        prepared = prepare_ambient(
            sources,
            sample_rate=sample_rate,
            duration_sec=2.0,
            seed=secrets.randbits(64),
        )
        self.play_prepared_ambient(prepared, volume)

    def play_prepared_ambient(
        self, prepared: PreparedAmbient, volume: float
    ) -> None:
        self._ambient_volume = min(1.0, max(0.0, float(volume)))
        if (
            self._ambient_sources == prepared.sources
            and self._ambient_channels
        ):
            effective_volume = self._channel_volume(len(self._ambient_channels))
            for channel in self._ambient_channels:
                channel.set_volume(effective_volume)
                channel.unpause()
            return

        mixer_settings = self._pygame.mixer.get_init()
        if mixer_settings is None:
            raise RuntimeError("Audio mixer is not initialized")
        sample_rate, sample_format, channels = mixer_settings
        if prepared.samples and sample_format != -16:
            raise RuntimeError("Ambient sound requires a signed 16-bit audio mixer")
        if prepared.samples and sample_rate != prepared.sample_rate:
            raise RuntimeError("Prepared ambient sample rate does not match the mixer")
        sounds: list[object] = []
        if prepared.samples:
            cache_key = ("generated", prepared.sources, sample_rate, channels)
            sound = self._ambient_cache.get(cache_key)
            if sound is None:
                pcm = prepared.samples if channels == 1 else array(
                    "h",
                    (
                        sample
                        for value in prepared.samples
                        for sample in (value,) * channels
                    ),
                )
                sound = self._pygame.mixer.Sound(buffer=pcm.tobytes())
                self._ambient_cache[cache_key] = sound
            sounds.append(sound)
        for path in prepared.recording_paths:
            cache_key = ("recording", str(path))
            sound = self._ambient_cache.get(cache_key)
            if sound is None:
                sound = self._pygame.mixer.Sound(str(path))
                self._ambient_cache[cache_key] = sound
            sounds.append(sound)

        self.stop_ambient()
        self._ambient_sounds = sounds
        try:
            effective_volume = self._channel_volume(len(sounds))
            for sound in sounds:
                channel = sound.play(loops=-1, fade_ms=250)
                if channel is None:
                    raise RuntimeError("No free audio channel is available")
                channel.set_volume(effective_volume)
                self._ambient_channels.append(channel)
        except Exception:
            self.stop_ambient()
            raise
        self._ambient_sources = prepared.sources

    def set_ambient_volume(self, volume: float) -> None:
        self._ambient_volume = min(1.0, max(0.0, float(volume)))
        effective_volume = self._channel_volume(len(self._ambient_channels))
        for channel in self._ambient_channels:
            channel.set_volume(effective_volume)

    def _channel_volume(self, channel_count: int) -> float:
        """Keep combined layers near the requested total power without clipping."""
        return self._ambient_volume / math.sqrt(max(1, channel_count))

    def pause_ambient(self) -> None:
        for channel in self._ambient_channels:
            channel.pause()

    def resume_ambient(self) -> None:
        for channel in self._ambient_channels:
            channel.unpause()

    def stop_ambient(self) -> None:
        for channel in self._ambient_channels:
            channel.stop()
        self._ambient_channels.clear()
        self._ambient_sounds.clear()
        self._ambient_sources = ()

    def close(self) -> None:
        self.stop_bell()
        self.stop_ambient()
        self._ambient_cache.clear()
        if self._pygame.mixer.get_init():
            self._pygame.mixer.quit()
