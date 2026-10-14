"""
Shared visual design system for generated PDF digital products.

Built in direct response to the owner comparing our chore chart to real
top-selling Etsy listings: "are you seeing how all these look versus
ours? how can we charge when ours is plain jane." Real competitors use
actual icon illustrations, playful rounded typography, and colorful
decorative treatment -- a plain data table in Helvetica was never going
to look like a real $5 product next to that.

This module is the shared look every generated PDF digital product now
uses: a real embedded font (Baloo 2, SIL Open Font License -- free to
embed in a sold product, see fonts/Baloo2-OFL.txt), a decorative two-tone
header with confetti-style accent dots, and a white rounded content card
over a tinted page background. Reused by chore_chart_generator.py (which
also places real per-task icon illustrations -- generated once via a
real AI call and committed as static assets under assets/icons/, never
regenerated per pipeline run) and pdf_generator.py's generic
checklist/table/tracker layouts (font + color + card only, no per-item
icons, since those items are real AI-generated text that varies every
run -- generating a custom icon per item isn't practical there).

Palette dict shape (see creative_director.py for the real themed
palettes): primary (header band), secondary (header stripe / accent
badge color), accent (page background tint), highlight (a third accent
color for variety), text (body text color).
"""
from __future__ import annotations

import random
from pathlib import Path

from reportlab.lib.colors import HexColor, white
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

PAGE_WIDTH, PAGE_HEIGHT = LETTER

_FONTS_DIR = Path(__file__).parent / "fonts"
ICONS_DIR = Path(__file__).parent / "assets" / "icons"

FONT_REGULAR = "Baloo2"
FONT_BOLD = "Baloo2-Bold"

_fonts_registered = False


def register_fonts() -> None:
    """Idempotent -- reportlab errors on re-registering the same font name
    in one process, and every PDF-generating call needs this done first."""
    global _fonts_registered
    if _fonts_registered:
        return
    pdfmetrics.registerFont(TTFont(FONT_REGULAR, str(_FONTS_DIR / "Baloo2-Regular.ttf")))
    pdfmetrics.registerFont(TTFont(FONT_BOLD, str(_FONTS_DIR / "Baloo2-Bold.ttf")))
    _fonts_registered = True


def icon_path(name: str) -> Path | None:
    """Returns the real committed icon asset for a known task name, or
    None if this task has no icon (caller falls back to a plain color
    badge with no image rather than crashing on a missing file)."""
    p = ICONS_DIR / f"{name}.png"
    return p if p.exists() else None


def _hex(c: str) -> str:
    return c if c.startswith("#") else f"#{c}"


def draw_page_background(c, *, palette: dict) -> None:
    c.setFillColor(HexColor(_hex(palette.get("accent", "#FFF8EC"))))
    c.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, fill=True, stroke=False)


def draw_decorative_header(c, title: str, subtitle: str, *, palette: dict,
                            header_h: float = 1.3 * inch, seed: int = 0) -> float:
    """Two-tone header band with scattered confetti dots, deliberately
    kept clear of the centered title text -- a real bug caught and fixed
    while building the very first mockup of this style: randomly-placed
    dots overlapped the title before this exclusion zone existed. Returns
    the y-coordinate just below the header, for callers to start content."""
    register_fonts()
    primary = HexColor(_hex(palette.get("primary", "#2EC4B6")))
    secondary = HexColor(_hex(palette.get("secondary", "#F26B6B")))
    highlight = HexColor(_hex(palette.get("highlight", "#FFC83D")))

    c.setFillColor(primary)
    c.rect(0, PAGE_HEIGHT - header_h, PAGE_WIDTH, header_h, fill=True, stroke=False)
    c.setFillColor(secondary)
    c.rect(0, PAGE_HEIGHT - header_h, PAGE_WIDTH, 0.1 * inch, fill=True, stroke=False)

    rng = random.Random(seed)
    dot_colors = [secondary, highlight, white]
    clear_left, clear_right = PAGE_WIDTH * 0.2, PAGE_WIDTH * 0.8
    for _ in range(16):
        x = rng.uniform(0.3 * inch, PAGE_WIDTH - 0.3 * inch)
        if clear_left < x < clear_right:
            continue
        y = rng.uniform(PAGE_HEIGHT - header_h + 0.2 * inch, PAGE_HEIGHT - 0.25 * inch)
        r = rng.uniform(0.025 * inch, 0.055 * inch)
        c.setFillColor(rng.choice(dot_colors))
        c.circle(x, y, r, fill=True, stroke=False)

    c.setFillColor(white)
    title_size = 26 if len(title) < 32 else 20
    title_y = PAGE_HEIGHT - header_h * 0.42 if subtitle else PAGE_HEIGHT - header_h * 0.55
    c.setFont(FONT_BOLD, title_size)
    c.drawCentredString(PAGE_WIDTH / 2, title_y, title)
    if subtitle:
        c.setFont(FONT_REGULAR, 11)
        c.drawCentredString(PAGE_WIDTH / 2, PAGE_HEIGHT - header_h * 0.72, subtitle)

    return PAGE_HEIGHT - header_h - 0.1 * inch


def draw_rounded_card(c, *, left: float, right: float, top: float, bottom: float, radius: float = 14) -> None:
    c.setFillColor(white)
    c.roundRect(left, bottom, right - left, top - bottom, radius, fill=True, stroke=False)


def draw_rounded_checkbox(c, form, *, name: str, tooltip: str, cx: float, cy: float,
                           size: float, accent_hex: str) -> None:
    """A checkbox sitting on a small rounded tile instead of bare on the
    page -- matches the softer, rounder look of real competing listings
    better than a plain square outline."""
    c.setFillColor(HexColor("#F4F4F4"))
    c.roundRect(cx - size / 2, cy - size / 2, size, size, size * 0.22, fill=True, stroke=False)
    box = size * 0.78
    form.checkbox(
        name=name, tooltip=tooltip, x=cx - box / 2, y=cy - box / 2, size=box,
        borderColor=HexColor(_hex(accent_hex)), fillColor=white, checked=False, relative=False,
    )


def draw_icon_badge(c, *, icon_file: Path | None, x: float, y: float, size: float, accent_hex: str) -> None:
    """A real icon illustration in a colored rounded-square badge, or just
    the colored badge alone (no image) if this task has no committed icon
    asset -- never crashes on a missing icon, just renders a plain accent."""
    c.setFillColor(HexColor(_hex(accent_hex)))
    c.roundRect(x - 3, y - 3, size + 6, size + 6, size * 0.16, fill=True, stroke=False)
    if icon_file is not None:
        c.drawImage(str(icon_file), x, y, width=size, height=size, mask="auto")
