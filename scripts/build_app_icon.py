#!/usr/bin/env python3
"""Build local Windows icon assets from a user-supplied square image."""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps


ROOT = Path(__file__).resolve().parents[1]


def square_image(source: Path) -> Image.Image:
    with Image.open(source) as image:
        image = ImageOps.exif_transpose(image).convert("RGBA")
        side = min(image.size)
        left = (image.width - side) // 2
        top = (image.height - side) // 2
        return image.crop((left, top, left + side, top + side))


def rounded_source(image: Image.Image, size: int) -> Image.Image:
    image = image.resize((size, size), Image.Resampling.LANCZOS)
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((1, 1, size - 2, size - 2), fill=255)
    output = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    output.paste(image, (0, 0), mask)
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument(
        "--output-dir",
        default=str(ROOT / "assets" / "local"),
    )
    args = parser.parse_args()

    source = Path(args.source).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    output = Path(args.output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    image = square_image(source)

    icon_path = output / "tafeiyu.ico"
    image.save(
        icon_path,
        format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    rounded_source(image, 256).save(output / "tafeiyu_icon.png")
    rounded_source(image, 64).save(output / "tafeiyu_titlebar.png")
    print(icon_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
