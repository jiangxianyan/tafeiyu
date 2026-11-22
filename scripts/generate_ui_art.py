#!/usr/bin/env python3
"""Generate deterministic, copyright-safe artwork for the desktop client."""

from __future__ import annotations

import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "assets" / "ui" / "tafeiyu_aurora.png"
WIDTH = 1600
HEIGHT = 1000


def lerp(a: int, b: int, t: float) -> int:
    return round(a + (b - a) * t)


def gradient() -> Image.Image:
    top = (6, 9, 18)
    bottom = (15, 21, 39)
    image = Image.new("RGB", (WIDTH, HEIGHT))
    pixels = image.load()
    for y in range(HEIGHT):
        t = y / max(1, HEIGHT - 1)
        color = tuple(lerp(top[i], bottom[i], t) for i in range(3))
        for x in range(WIDTH):
            pixels[x, y] = color
    return image


def radial_glow(
    base: Image.Image,
    center: tuple[int, int],
    radius: int,
    color: tuple[int, int, int],
    opacity: int,
) -> None:
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    pixels = layer.load()
    cx, cy = center
    for y in range(max(0, cy - radius), min(HEIGHT, cy + radius)):
        for x in range(max(0, cx - radius), min(WIDTH, cx + radius)):
            distance = math.hypot(x - cx, y - cy)
            if distance >= radius:
                continue
            strength = (1 - distance / radius) ** 2.2
            pixels[x, y] = (*color, round(opacity * strength))
    base.alpha_composite(layer)


def draw_aurora(base: Image.Image) -> None:
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    points = []
    for x in range(-100, WIDTH + 120, 20):
        y = 190 + 95 * math.sin(x / 270) + 45 * math.sin(x / 97)
        points.append((x, y))
    thickness = 110
    for index, (x, y) in enumerate(points):
        alpha = 18 + 16 * math.sin(index / 7)
        draw.ellipse(
            (x - 90, y - thickness, x + 90, y + thickness),
            fill=(255, 94, 169, max(8, round(alpha))),
        )
    layer = layer.filter(ImageFilter.GaussianBlur(45))
    base.alpha_composite(layer)

    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    for x in range(-100, WIDTH + 120, 24):
        y = 420 + 120 * math.sin(x / 360 + 1.5) + 55 * math.sin(x / 130)
        draw.ellipse(
            (x - 115, y - 70, x + 115, y + 70),
            fill=(74, 192, 255, 11),
        )
    layer = layer.filter(ImageFilter.GaussianBlur(55))
    base.alpha_composite(layer)


def draw_constellation(base: Image.Image) -> None:
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    rng = random.Random(20261122)
    stars = [
        (rng.randint(40, WIDTH - 40), rng.randint(40, HEIGHT - 40))
        for _ in range(115)
    ]
    for index, (x, y) in enumerate(stars):
        radius = rng.choice((0.6, 0.8, 1.0, 1.3, 1.8))
        alpha = rng.randint(25, 95)
        draw.ellipse(
            (x - radius, y - radius, x + radius, y + radius),
            fill=(225, 236, 255, alpha),
        )
        if index % 9 == 0 and index + 1 < len(stars):
            nx, ny = stars[index + 1]
            if math.hypot(nx - x, ny - y) < 230:
                draw.line((x, y, nx, ny), fill=(117, 161, 221, 22), width=1)
    base.alpha_composite(layer)


def draw_whale_mark(base: Image.Image) -> None:
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    cx, cy = 1260, 580
    color = (255, 132, 185, 60)
    draw.arc((cx - 160, cy - 95, cx + 110, cy + 105), 20, 230, fill=color, width=8)
    draw.polygon(
        [
            (cx - 95, cy + 30),
            (cx - 170, cy - 20),
            (cx - 155, cy + 55),
        ],
        fill=(103, 216, 255, 47),
    )
    draw.ellipse((cx - 30, cy - 23, cx - 18, cy - 11), fill=(255, 255, 255, 90))
    layer = layer.filter(ImageFilter.GaussianBlur(1.2))
    base.alpha_composite(layer)


def main() -> int:
    base = gradient().convert("RGBA")
    radial_glow(base, (1350, 330), 620, (255, 94, 170), 72)
    radial_glow(base, (240, 670), 530, (53, 170, 255), 58)
    radial_glow(base, (830, 100), 360, (151, 94, 255), 26)
    draw_aurora(base)
    draw_constellation(base)
    draw_whale_mark(base)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    base.convert("RGB").save(OUTPUT, quality=92, optimize=True)
    print(OUTPUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
