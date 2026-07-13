#!/usr/bin/env python3
"""Compose exact MVN Climate Atlas engineering overlays over approved base scenes."""

from pathlib import Path
from math import cos, pi, sin

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parent
LAYERS = ROOT / "layers"
REVISIONS = ROOT / "revisions" / "generated"
FINALS = ROOT / "finals"
OVERLAYS = ROOT / "overlays"

TEAL = (17, 184, 178, 210)
DEEP = (7, 94, 99, 220)
AMBER = (242, 169, 59, 205)
CORAL = (229, 106, 93, 205)
ICE = (234, 247, 246, 125)
WHITE = (247, 245, 240, 235)
SCALE = 4


def scaled(points):
    return [(round(x * SCALE), round(y * SCALE)) for x, y in points]


def bezier(p0, p1, p2, p3, steps=120):
    points = []
    for index in range(steps + 1):
        t = index / steps
        u = 1 - t
        x = u**3 * p0[0] + 3 * u**2 * t * p1[0] + 3 * u * t**2 * p2[0] + t**3 * p3[0]
        y = u**3 * p0[1] + 3 * u**2 * t * p1[1] + 3 * u * t**2 * p2[1] + t**3 * p3[1]
        points.append((round(x), round(y)))
    return points


def line(draw, points, color=TEAL, width=7):
    draw.line(scaled(points), fill=color, width=width * SCALE, joint="curve")


def curve(draw, p0, p1, p2, p3, color=TEAL, width=7, arrow=True):
    points = bezier(p0, p1, p2, p3)
    line(draw, points, color, width)
    if arrow:
        arrow_head(draw, points[-1], points[-7], color, width)


def dashed_curve(draw, p0, p1, p2, p3, color=TEAL, width=5):
    points = bezier(p0, p1, p2, p3, 160)
    for index in range(0, len(points) - 6, 12):
        line(draw, points[index:index + 7], color, width)


def arrow_head(draw, tip, previous, color=TEAL, width=7, size=18):
    angle = __import__("math").atan2(tip[1] - previous[1], tip[0] - previous[0])
    left = (tip[0] - size * cos(angle - pi / 5), tip[1] - size * sin(angle - pi / 5))
    right = (tip[0] - size * cos(angle + pi / 5), tip[1] - size * sin(angle + pi / 5))
    line(draw, [left, tip, right], color, width)


def ellipse(draw, box, fill=None, outline=DEEP, width=4):
    draw.ellipse(tuple(round(v * SCALE) for v in box), fill=fill, outline=outline, width=width * SCALE)


def rounded_rect(draw, box, radius=18, fill=None, outline=DEEP, width=4):
    draw.rounded_rectangle(
        tuple(round(v * SCALE) for v in box),
        radius=radius * SCALE,
        fill=fill,
        outline=outline,
        width=width * SCALE,
    )


def measurement_dot(draw, x, y):
    ellipse(draw, (x - 10, y - 10, x + 10, y + 10), fill=DEEP, outline=WHITE, width=2)


def compose(base_path, output_name, painter):
    base = Image.open(base_path).convert("RGBA")
    overlay_large = Image.new("RGBA", (base.width * SCALE, base.height * SCALE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay_large)
    painter(draw)
    overlay = overlay_large.resize(base.size, Image.Resampling.LANCZOS)
    FINALS.mkdir(parents=True, exist_ok=True)
    OVERLAYS.mkdir(parents=True, exist_ok=True)
    overlay.save(OVERLAYS / output_name)
    final = Image.alpha_composite(base, overlay).convert("RGB")
    final.save(FINALS / output_name, "PNG", optimize=True)


def filters(draw):
    # One compact three-line bundle: intake through the dominant washable mesh.
    for dx in (0, 32, 64):
        curve(draw, (560 + dx, 120), (550 + dx, 260), (600 + dx, 520), (760 + dx, 735), TEAL, 7)
    rounded_rect(draw, (330, 245, 1210, 625), 26, None, DEEP, 4)
    rounded_rect(draw, (1220, 385, 1365, 565), 18, None, AMBER, 4)


def inverter(draw):
    for offset in (0, 28, 56):
        curve(draw, (325 + offset, 180), (320 + offset, 240), (280 + offset, 305), (235 + offset, 360), TEAL, 6)
        # Deliberately pulsed On/Off flow on the right.
        line(draw, [(1250 + offset, 180), (1240 + offset, 225)], AMBER, 6)
        line(draw, [(1225 + offset, 255), (1200 + offset, 300)], AMBER, 6)
        line(draw, [(1175 + offset, 330), (1145 + offset, 365)], AMBER, 6)
    # Stable modulation curve versus stepped cycling, without labels.
    curve(draw, (190, 520), (290, 475), (390, 565), (500, 520), TEAL, 5, False)
    line(draw, [(1160, 500), (1225, 500), (1225, 545), (1290, 545), (1290, 500), (1360, 500)], AMBER, 5)
    measurement_dot(draw, 805, 420)


def btu(draw):
    # Teal comfort field. Heat sources stay readable without a decorative grid.
    ellipse(draw, (450, 445, 1190, 800), fill=ICE, outline=(17, 184, 178, 115), width=3)
    # Four exact heat-load cues: sun, person, television, kitchen.
    for x, y, radius in [(330, 280, 34), (650, 545, 24), (970, 350, 28), (1325, 390, 30)]:
        ellipse(draw, (x - radius, y - radius, x + radius, y + radius), None, AMBER, 4)
        for angle in range(0, 360, 90):
            ax = x + (radius + 10) * cos(angle * pi / 180)
            ay = y + (radius + 10) * sin(angle * pi / 180)
            bx = x + (radius + 22) * cos(angle * pi / 180)
            by = y + (radius + 22) * sin(angle * pi / 180)
            line(draw, [(ax, ay), (bx, by)], AMBER, 3)
    for offset in (0, 22, 44):
        curve(draw, (620 + offset, 150), (670 + offset, 210), (720 + offset, 270), (770 + offset, 325), TEAL, 5)


def multisplit(draw):
    # Shared left outdoor unit: one trunk with three tidy architectural branches.
    shared = (165, 770)
    line(draw, [shared, (190, 610), (190, 505)], TEAL, 4)
    line(draw, [(190, 505), (300, 505), (300, 282), (495, 282)], TEAL, 4)
    line(draw, [(190, 505), (600, 505), (600, 300), (930, 300)], TEAL, 4)
    line(draw, [(190, 610), (270, 610), (270, 545), (360, 545)], TEAL, 4)
    ellipse(draw, (115, 720, 215, 820), None, AMBER, 5)
    # Three independent right systems: separate paths, no shared trunk.
    line(draw, [(1375, 840), (1350, 650), (1200, 650), (1200, 585), (1120, 585)], DEEP, 4)
    line(draw, [(1440, 810), (1415, 510), (1300, 510), (1300, 245), (1160, 245)], DEEP, 4)
    line(draw, [(1500, 780), (1460, 720), (1000, 720), (1000, 545), (830, 545)], DEEP, 4)


def heating(draw):
    # Energy transfer loop through the wall.
    curve(draw, (400, 690), (520, 650), (650, 330), (1010, 185), TEAL, 7, True)
    curve(draw, (1010, 215), (720, 360), (560, 720), (420, 745), DEEP, 5, True)
    # Warm supply air inside.
    for offset in (0, 28, 56):
        curve(draw, (1060 + offset, 200), (1120 + offset, 250), (1170 + offset, 330), (1210 + offset, 420), AMBER, 7)
    measurement_dot(draw, 1235, 490)


def semi_industrial(draw):
    # Duct diffusers: two short three-line drops.
    for cx, cy in [(475, 350), (310, 410)]:
        for dx in (-12, 0, 12):
            curve(draw, (cx + dx, cy), (cx + dx, cy + 35), (cx + dx + 8, cy + 60), (cx + dx + 15, cy + 85), TEAL, 3)
    # Cassette: four-direction distribution.
    for end in [(680, 220), (920, 220), (800, 330), (800, 75)]:
        curve(draw, (800, 145), (800, 160), ((800 + end[0]) / 2, (145 + end[1]) / 2), end, TEAL, 4)
    # Floor-ceiling throw along the central room.
    for dy in (0, 18, 36):
        curve(draw, (760, 405 + dy), (850, 420 + dy), (930, 450 + dy), (1010, 485 + dy), TEAL, 4)
    # Column unit sends air upward and into the tall retail zone.
    for dx in (-15, 0, 15):
        curve(draw, (1455 + dx, 380), (1450 + dx, 330), (1430 + dx, 280), (1400 + dx, 235), TEAL, 4)


def fresh_air(draw):
    # Thin fresh-air path from the outdoor intake through the wall to the unit.
    curve(draw, (455, 445), (580, 430), (920, 235), (1340, 250), TEAL, 6, True)
    # Larger dashed recirculation loop in the bedroom.
    dashed_curve(draw, (1040, 610), (1160, 520), (1240, 380), (1380, 285), DEEP, 5)
    for offset in (0, 24, 48):
        curve(draw, (1400 + offset, 290), (1360 + offset, 350), (1260 + offset, 430), (1140 + offset, 520), TEAL, 6)
    measurement_dot(draw, 1230, 610)


def sound_icon(draw, x, y):
    line(draw, [(x - 20, y - 12), (x - 5, y - 12), (x + 10, y - 28), (x + 10, y + 28), (x - 5, y + 12), (x - 20, y + 12)], DEEP, 4)
    curve(draw, (x + 18, y - 18), (x + 35, y - 10), (x + 35, y + 10), (x + 18, y + 18), DEEP, 3, False)


def snow_icon(draw, x, y):
    for angle in (0, 60, 120):
        dx, dy = 30 * cos(angle * pi / 180), 30 * sin(angle * pi / 180)
        line(draw, [(x - dx, y - dy), (x + dx, y + dy)], DEEP, 3)


def wrench_icon(draw, x, y):
    ellipse(draw, (x - 26, y - 26, x + 8, y + 8), None, DEEP, 4)
    line(draw, [(x - 3, y + 3), (x + 30, y + 36)], DEEP, 7)


def gear_icon(draw, x, y):
    ellipse(draw, (x - 28, y - 28, x + 28, y + 28), None, DEEP, 4)
    ellipse(draw, (x - 9, y - 9, x + 9, y + 9), None, DEEP, 4)
    for angle in range(0, 360, 45):
        a = angle * pi / 180
        line(draw, [(x + 28 * cos(a), y + 28 * sin(a)), (x + 40 * cos(a), y + 40 * sin(a))], DEEP, 4)


def brands(draw):
    for x, y, painter in [(250, 220, sound_icon), (1420, 220, snow_icon), (250, 710, wrench_icon), (1420, 710, gear_icon)]:
        ellipse(draw, (x - 58, y - 58, x + 58, y + 58), fill=(234, 247, 246, 165), outline=TEAL, width=4)
        painter(draw, x, y)
    # One small engineering bracket under the exploded product family.
    line(draw, [(520, 810), (520, 845), (1150, 845), (1150, 810)], DEEP, 4)


def wifi(draw):
    # Exact dotted link between phone and unit.
    dashed_curve(draw, (402, 430), (650, 320), (980, 190), (1240, 205), DEEP, 5)
    for offset in (0, 24, 48):
        curve(draw, (1280 + offset, 245), (1250 + offset, 310), (1160 + offset, 390), (1060 + offset, 455), TEAL, 6)
    measurement_dot(draw, 1090, 560)
    # Restrained warm exterior cue at the doorway.
    rounded_rect(draw, (210, 245, 465, 820), 26, (242, 169, 59, 30), AMBER, 3)


def main():
    jobs = [
        (LAYERS / "filters-hero-base.png", "filtry-v-kondicionere-hero.png", filters),
        (REVISIONS / "inverter-hero-base-v2.png", "inverter-vs-onoff-hero.png", inverter),
        (REVISIONS / "btu-hero-base-v2.png", "kak-rasschitat-moshnost-btu-hero.png", btu),
        (REVISIONS / "multisplit-hero-base-v2.png", "multisplit-vs-split-system-comparison-hero.png", multisplit),
        (REVISIONS / "heating-hero-base-v2.png", "obogrev-kondicionerom-osen-hero.png", heating),
        (REVISIONS / "semi-industrial-hero-base-v2.png", "polupromyshlennye-kondicionery-hero.png", semi_industrial),
        (LAYERS / "fresh-air-hero-base.png", "pritok-vozduha-hero.png", fresh_air),
        (LAYERS / "brands-hero-base.png", "top-brendov-kondicionerov-hero.png", brands),
        (LAYERS / "wifi-hero-base.png", "umniy-kondicioner-hero.png", wifi),
    ]
    for base_path, output_name, painter in jobs:
        compose(base_path, output_name, painter)
        print(FINALS / output_name)


if __name__ == "__main__":
    main()
