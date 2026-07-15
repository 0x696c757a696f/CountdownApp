from __future__ import annotations

import math
import random
from array import array


NOISE_KINDS = {"white", "pink", "brown", "grey"}


def synthesize_mono(
    kind: str,
    *,
    sample_rate: int = 44_100,
    duration_sec: float = 2.0,
    seed: int | None = None,
) -> array:
    """Create bounded 16-bit mono PCM for a looping ambient source."""
    if sample_rate <= 0 or duration_sec <= 0:
        raise ValueError("Sample rate and duration must be positive")
    sample_count = max(1, round(sample_rate * duration_sec))
    if kind.startswith("tone:"):
        try:
            frequency = float(kind.partition(":")[2])
        except ValueError:
            raise ValueError(f"Invalid tone: {kind}") from None
        if not 0 < frequency < sample_rate / 2:
            raise ValueError(f"Tone is outside the playable range: {frequency}")
        amplitude = 0.28 * 32_767
        return array(
            "h",
            (
                round(amplitude * math.sin(2 * math.pi * frequency * index / sample_rate))
                for index in range(sample_count)
            ),
        )
    if kind not in NOISE_KINDS:
        raise ValueError(f"Unknown ambient sound: {kind}")

    overlap = min(max(16, round(sample_rate * 0.03)), max(1, sample_count // 4))
    generator = random.Random(seed)
    raw_count = sample_count + overlap
    white = [generator.uniform(-1.0, 1.0) for _ in range(raw_count)]

    if kind == "white":
        shaped = white
    elif kind == "pink":
        shaped = _pink_noise(white)
    elif kind == "brown":
        shaped = _brown_noise(white)
    else:
        shaped = _grey_noise(white)

    loop = shaped[:sample_count]
    for index in range(overlap):
        ratio = index / overlap
        loop[index] = shaped[sample_count + index] * (1.0 - ratio) + loop[index] * ratio

    mean = sum(loop) / len(loop)
    centered = [value - mean for value in loop]
    peak = max(max(abs(value) for value in centered), 1e-9)
    scale = 0.28 * 32_767 / peak
    return array("h", (round(value * scale) for value in centered))


def synthesize_mix(
    sources: tuple[str, ...],
    *,
    sample_rate: int = 44_100,
    duration_sec: float = 2.0,
    seed: int | None = None,
) -> array:
    """Mix one or more ambient sources without allowing integer clipping."""
    active = tuple(source for source in sources if source != "off")
    if not active:
        raise ValueError("At least one ambient source is required")
    layers = [
        synthesize_mono(
            source,
            sample_rate=sample_rate,
            duration_sec=duration_sec,
            seed=seed,
        )
        for source in active
    ]
    if len(layers) == 1:
        return layers[0]
    divisor = len(layers)
    return array(
        "h",
        (
            round(sum(values) / divisor)
            for values in zip(*(layer for layer in layers))
        ),
    )


def _pink_noise(white: list[float]) -> list[float]:
    b0 = b1 = b2 = b3 = b4 = b5 = b6 = 0.0
    result: list[float] = []
    for value in white:
        b0 = 0.99886 * b0 + value * 0.0555179
        b1 = 0.99332 * b1 + value * 0.0750759
        b2 = 0.96900 * b2 + value * 0.1538520
        b3 = 0.86650 * b3 + value * 0.3104856
        b4 = 0.55000 * b4 + value * 0.5329522
        b5 = -0.7616 * b5 - value * 0.0168980
        result.append(b0 + b1 + b2 + b3 + b4 + b5 + b6 + value * 0.5362)
        b6 = value * 0.115926
    return result


def _brown_noise(white: list[float]) -> list[float]:
    """Create low-frequency-weighted Brownian noise with bounded drift."""
    previous = 0.0
    result: list[float] = []
    for value in white:
        previous = (previous + 0.02 * value) / 1.02
        result.append(previous)
    return result


def _grey_noise(white: list[float]) -> list[float]:
    """Approximate equal-loudness noise with restrained low/high emphasis."""
    slow = 0.0
    medium = 0.0
    result: list[float] = []
    for value in white:
        slow += 0.004 * (value - slow)
        medium += 0.06 * (value - medium)
        high = value - medium
        result.append(0.52 * value + 1.15 * slow + 0.22 * high)
    return result
