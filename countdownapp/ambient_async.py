from __future__ import annotations

import logging
import secrets
import threading
from array import array
from collections.abc import Callable
from concurrent.futures import Executor, Future, ThreadPoolExecutor
from dataclasses import dataclass

from .ambient import synthesize_mix


@dataclass(frozen=True)
class PreparedAmbient:
    sources: tuple[str, ...]
    samples: array
    sample_rate: int


class AsyncAmbientController:
    """Prepares only the latest requested ambient mix away from the GUI thread."""

    SAMPLE_RATE = 44_100
    DURATION_SEC = 2.0

    def __init__(
        self,
        player: Callable[[PreparedAmbient, float], bool],
        dispatch: Callable[[Callable[[], None]], None],
        *,
        renderer: Callable[[tuple[str, ...]], PreparedAmbient] | None = None,
        executor: Executor | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._player = player
        self._dispatch = dispatch
        self._renderer = renderer or self._render
        self._executor = executor or ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="ambient-render"
        )
        self._owns_executor = executor is None
        self._logger = logger or logging.getLogger(__name__)
        self._lock = threading.Lock()
        self._generation = 0
        self._future: Future | None = None
        self._closed = False
        self._volume = 0.0

    def request(
        self,
        noise: str,
        tone: str,
        volume: float,
        on_complete: Callable[[bool], None] | None = None,
    ) -> None:
        sources = tuple(source for source in (noise, tone) if source != "off")
        with self._lock:
            if self._closed:
                return
            self._generation += 1
            generation = self._generation
            self._volume = min(1.0, max(0.0, float(volume)))
            if self._future is not None:
                self._future.cancel()
            future = self._executor.submit(self._renderer, sources)
            self._future = future
        future.add_done_callback(
            lambda completed: self._render_finished(
                generation, completed, volume, on_complete
            )
        )

    def set_volume(self, volume: float) -> None:
        with self._lock:
            self._volume = min(1.0, max(0.0, float(volume)))

    def cancel(self) -> None:
        with self._lock:
            self._generation += 1
            if self._future is not None:
                self._future.cancel()
                self._future = None

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
        self.cancel()
        if self._owns_executor:
            self._executor.shutdown(wait=False, cancel_futures=True)

    def _render_finished(
        self,
        generation: int,
        future: Future,
        volume: float,
        on_complete: Callable[[bool], None] | None,
    ) -> None:
        with self._lock:
            if self._closed or generation != self._generation:
                return
        try:
            prepared = future.result()
        except Exception as error:
            self._logger.warning("Ambient rendering failed: %s", error)
            self._dispatch_safely(
                lambda: self._complete_if_current(
                    generation, None, volume, on_complete
                )
            )
            return
        self._dispatch_safely(
            lambda: self._complete_if_current(
                generation, prepared, volume, on_complete
            )
        )

    def _complete_if_current(
        self,
        generation: int,
        prepared: PreparedAmbient | None,
        volume: float,
        on_complete: Callable[[bool], None] | None,
    ) -> None:
        with self._lock:
            if self._closed or generation != self._generation:
                return
            self._future = None
            volume = self._volume
        played = False
        if prepared is not None:
            try:
                played = self._player(prepared, volume)
            except Exception as error:
                self._logger.warning("Prepared ambient playback failed: %s", error)
        if on_complete is not None:
            on_complete(played)

    def _dispatch_safely(self, callback: Callable[[], None]) -> None:
        try:
            self._dispatch(callback)
        except Exception as error:
            self._logger.debug("Ambient completion dispatch was discarded: %s", error)

    @classmethod
    def _render(cls, sources: tuple[str, ...]) -> PreparedAmbient:
        samples = synthesize_mix(
            sources,
            sample_rate=cls.SAMPLE_RATE,
            duration_sec=cls.DURATION_SEC,
            seed=secrets.randbits(64),
        )
        return PreparedAmbient(sources, samples, cls.SAMPLE_RATE)
