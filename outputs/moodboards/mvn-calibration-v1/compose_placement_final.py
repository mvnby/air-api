#!/usr/bin/env python3
"""Build the exact MVN AirFlow layer over the approved generated bedroom plate."""

from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parent
BASE = ROOT / "generated" / "8a6b41893336a356367d4f26dbd2508a.png"
OVERLAY = ROOT / "generated" / "placement-bedroom-airflow-overlay.png"
OUTPUT = ROOT / "generated" / "placement-bedroom-calibration-final.png"

TEAL = (17, 184, 178, 215)
DEEP_TEAL = (7, 94, 99, 235)
CORAL = (229, 106, 93, 205)


def bezier(p0, p1, p2, p3, steps=140):
    points = []
    for index in range(steps + 1):
        t = index / steps
        u = 1 - t
        x = u**3 * p0[0] + 3 * u**2 * t * p1[0] + 3 * u * t**2 * p2[0] + t**3 * p3[0]
        y = u**3 * p0[1] + 3 * u**2 * t * p1[1] + 3 * u * t**2 * p2[1] + t**3 * p3[1]
        points.append((round(x), round(y)))
    return points


def scale_points(points, factor):
    return [(round(x * factor), round(y * factor)) for x, y in points]


def main():
    base = Image.open(BASE).convert("RGBA")
    width, height = base.size
    factor = 4
    overlay_large = Image.new("RGBA", (width * factor, height * factor), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay_large)

    # Three independent, unbranched lanes. Geometry is deterministic and reusable.
    lanes = [
        ((1290, 278), (1090, 295), (760, 340), (430, 360)),
        ((1350, 278), (1120, 330), (780, 420), (430, 440)),
        ((1410, 278), (1140, 375), (800, 500), (430, 520)),
    ]
    for start, control_1, control_2, end in lanes:
        points = bezier(start, control_1, control_2, end)
        draw.line(scale_points(points, factor), fill=TEAL, width=8 * factor, joint="curve")
        tip_x, tip_y = end
        chevron = [(tip_x + 24, tip_y - 16), (tip_x, tip_y), (tip_x + 24, tip_y + 16)]
        draw.line(scale_points(chevron, factor), fill=TEAL, width=8 * factor, joint="curve")

    # Wrong-position ghost: one outline and one X, with no airflow attached.
    ghost_box = tuple(round(value * factor) for value in (155, 145, 405, 235))
    draw.rounded_rectangle(ghost_box, radius=24 * factor, outline=CORAL, width=4 * factor)
    draw.line(scale_points([(185, 215), (375, 215)], factor), fill=CORAL, width=4 * factor)
    draw.line(scale_points([(445, 165), (505, 225)], factor), fill=CORAL, width=9 * factor)
    draw.line(scale_points([(505, 165), (445, 225)], factor), fill=CORAL, width=9 * factor)

    # MVN measurement point near pillow height.
    center = (1168 * factor, 485 * factor)
    radius = 10 * factor
    draw.ellipse(
        (center[0] - radius, center[1] - radius, center[0] + radius, center[1] + radius),
        fill=DEEP_TEAL,
        outline=(247, 245, 240, 255),
        width=2 * factor,
    )

    overlay = overlay_large.resize((width, height), Image.Resampling.LANCZOS)
    final = Image.alpha_composite(base, overlay)
    overlay.save(OVERLAY)
    final.convert("RGB").save(OUTPUT, quality=96)
    print(OUTPUT)


if __name__ == "__main__":
    main()
