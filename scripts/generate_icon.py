from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
MASTER_SIZE = 512
RENDER_SCALE = 4
ICO_SIZES = (16, 20, 24, 32, 48, 64, 128, 256)

NAVY = "#172033"
BLUE = "#4169e1"
GREEN = "#62d995"
WHITE = "#f8fafc"


def generate_compact_icon(output_size: int) -> Image.Image:
    """Render shell-sized artwork on whole pixels so Windows cannot blur it."""
    image = Image.new("RGBA", (output_size, output_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    last = output_size - 2
    draw.ellipse((1, 1, last, last), fill=NAVY)

    arc_inset = 2 if output_size <= 20 else 3
    arc_width = max(2, round(output_size * 0.14))
    draw.arc(
        (arc_inset, arc_inset, output_size - arc_inset - 1, output_size - arc_inset - 1),
        start=15,
        end=315,
        fill=BLUE,
        width=arc_width,
    )

    center = (round(output_size * 0.48), round(output_size * 0.53))
    hand_width = max(2, round(output_size * 0.12))
    draw.line(
        (center, (center[0], round(output_size * 0.29))),
        fill=WHITE,
        width=hand_width,
    )
    draw.line(
        (center, (round(output_size * 0.70), round(output_size * 0.70))),
        fill=WHITE,
        width=hand_width,
    )
    hand_radius = max(1, hand_width // 2)
    draw.ellipse(
        (
            center[0] - hand_radius,
            center[1] - hand_radius,
            center[0] + hand_radius,
            center[1] + hand_radius,
        ),
        fill=WHITE,
    )

    node_center = (round(output_size * 0.77), round(output_size * 0.25))
    node_radius = max(1, round(output_size * 0.08))
    draw.ellipse(
        (
            node_center[0] - node_radius,
            node_center[1] - node_radius,
            node_center[0] + node_radius,
            node_center[1] + node_radius,
        ),
        fill=GREEN,
    )
    return image


def generate_icon(output_size: int = MASTER_SIZE) -> Image.Image:
    if output_size <= 24:
        return generate_compact_icon(output_size)
    size = MASTER_SIZE * RENDER_SCALE
    scale = RENDER_SCALE
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    def box(left: int, top: int, right: int, bottom: int) -> tuple[int, ...]:
        return tuple(value * scale for value in (left, top, right, bottom))

    draw.ellipse(box(38, 38, 474, 474), fill=NAVY)
    draw.arc(
        box(61, 61, 451, 451),
        start=15,
        end=315,
        fill=BLUE,
        width=48 * scale,
    )

    center = (244 * scale, 270 * scale)
    hands = ((244, 154), (335, 337))
    hand_width = 30 * scale
    hand_radius = hand_width // 2
    for target_x, target_y in hands:
        target = (target_x * scale, target_y * scale)
        draw.line((center, target), fill=WHITE, width=hand_width)
        draw.ellipse(
            (
                target[0] - hand_radius,
                target[1] - hand_radius,
                target[0] + hand_radius,
                target[1] + hand_radius,
            ),
            fill=WHITE,
        )
    draw.ellipse(box(222, 248, 266, 292), fill=WHITE)

    angle = math.radians(-42)
    node_x = 256 + round(195 * math.cos(angle))
    node_y = 256 + round(195 * math.sin(angle))
    draw.ellipse(
        box(node_x - 35, node_y - 35, node_x + 35, node_y + 35),
        fill=GREEN,
    )

    return image.resize(
        (output_size, output_size),
        Image.Resampling.LANCZOS,
    )


def main() -> None:
    master = generate_icon()
    master.save(ROOT / "clock_icon.png", optimize=True)
    icon_frames = [generate_icon(size) for size in ICO_SIZES]
    icon_frames[-1].save(
        ROOT / "clock_icon.ico",
        format="ICO",
        sizes=[(size, size) for size in ICO_SIZES],
        append_images=icon_frames[:-1],
    )


if __name__ == "__main__":
    main()
