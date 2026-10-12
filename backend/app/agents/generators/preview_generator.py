"""Generates a real PNG listing-preview image (spec section 9 / Etsy convention: 2000x2000 recommended)."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

PREVIEW_SIZE = (2000, 2000)


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def generate_preview_png(path: Path, *, title: str, palette: dict) -> None:
    bg = _hex_to_rgb(palette.get("primary", "#1B4332"))
    fg = _hex_to_rgb(palette.get("accent", "#D8F3DC"))

    img = Image.new("RGB", PREVIEW_SIZE, color=bg)
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype("arial.ttf", 90)
        font_small = ImageFont.truetype("arial.ttf", 48)
    except OSError:
        font = ImageFont.load_default()
        font_small = ImageFont.load_default()

    # Wrap title across multiple lines so it fits the canvas.
    words = title.split()
    lines: list[str] = []
    current = ""
    for word in words:
        test = f"{current} {word}".strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] > PREVIEW_SIZE[0] - 200:
            lines.append(current)
            current = word
        else:
            current = test
    if current:
        lines.append(current)

    total_height = len(lines) * 110
    y = (PREVIEW_SIZE[1] - total_height) // 2 - 60
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        w = bbox[2] - bbox[0]
        draw.text(((PREVIEW_SIZE[0] - w) / 2, y), line, fill=fg, font=font)
        y += 110

    footer = "ULTRON Commerce"
    bbox = draw.textbbox((0, 0), footer, font=font_small)
    w = bbox[2] - bbox[0]
    draw.text(((PREVIEW_SIZE[0] - w) / 2, PREVIEW_SIZE[1] - 150), footer, fill=fg, font=font_small)

    img.save(path, "PNG")
