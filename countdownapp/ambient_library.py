from __future__ import annotations

from array import array
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .ambient import synthesize_mix
from .resources import resource_path


RECORDING_RESOURCES = {
    "recording:storm": "ambient_storm.ogg",
    "recording:rain": "ambient_rain.ogg",
}


@dataclass(frozen=True)
class AmbientPlan:
    synthetic_sources: tuple[str, ...]
    recording_paths: tuple[Path, ...]


@dataclass(frozen=True)
class PreparedAmbient:
    sources: tuple[str, ...]
    samples: array
    sample_rate: int
    recording_paths: tuple[Path, ...] = ()


def build_ambient_plan(
    sources: tuple[str, ...],
    *,
    resolve_resource: Callable[[str], Path] = resource_path,
) -> AmbientPlan:
    """Separate generated layers from bundled recording layers."""
    active = tuple(source for source in sources if source != "off")
    synthetic = tuple(source for source in active if source not in RECORDING_RESOURCES)
    recordings = tuple(
        resolve_resource(RECORDING_RESOURCES[source])
        for source in active
        if source in RECORDING_RESOURCES
    )
    return AmbientPlan(synthetic, recordings)


def prepare_ambient(
    sources: tuple[str, ...],
    *,
    sample_rate: int,
    duration_sec: float,
    seed: int,
    resolve_resource: Callable[[str], Path] = resource_path,
) -> PreparedAmbient:
    """Prepare generated PCM while retaining bundled recordings as separate layers."""
    active = tuple(source for source in sources if source != "off")
    plan = build_ambient_plan(active, resolve_resource=resolve_resource)
    samples = (
        synthesize_mix(
            plan.synthetic_sources,
            sample_rate=sample_rate,
            duration_sec=duration_sec,
            seed=seed,
        )
        if plan.synthetic_sources
        else array("h")
    )
    return PreparedAmbient(active, samples, sample_rate, plan.recording_paths)
