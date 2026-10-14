"""
Generates an actual, openable, correctly-dimensioned PDF (spec section 9).

`sections` accepts either the old plain `list[str]` (each one rendered as
a ruled notes page -- kept for when no real content plan is available) or
a real, researched content plan: `list[dict]`, each with a "heading", a
"layout" ("checklist" | "table" | "tracker" | "notes"), and whatever that
layout needs ("items" for checklist, "columns" for table, "periods"/
"period_label" for tracker). See digital_production.py's
_real_content_plan() for how the dict form is actually built, from real
competitive research rather than a single flat hardcoded template --
built in direct response to the owner's "super super basic compared to
ones selling for $5 on Etsy" feedback on the old generic-fallback pages.

checklist/tracker items are real fillable AcroForm checkboxes, not just
drawn rectangles -- the single strongest real signal found in this
session's competitive research (chore charts) was "editable," and nothing
about that signal is chore-chart-specific.

Visual design (2026-10-14, "how can we charge when ours is plain jane"):
shares design_system.py with chore_chart_generator.py -- the real
embedded font, decorative header, and white rounded content card -- so
EVERY generic digital product gets the same visual lift, not just chore
charts. Deliberately NOT given per-item icon illustrations the way the
chore chart's fixed task vocabulary got: these items are real AI-generated
text that's different every single run (a wedding checklist's 15 items
this run won't be the same 15 next run), so generating a custom icon per
item isn't practical the way it was for a small, fixed, reused task list.
"""
from __future__ import annotations

from pathlib import Path

from reportlab.lib.colors import HexColor, white
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

from app.agents.generators.design_system import (
    FONT_BOLD,
    FONT_REGULAR,
    PAGE_HEIGHT,
    PAGE_WIDTH,
    draw_decorative_header,
    draw_page_background,
    draw_rounded_card,
    draw_rounded_checkbox,
    register_fonts,
)

CARD_LEFT = 0.6 * inch
CARD_RIGHT = PAGE_WIDTH - 0.6 * inch
CARD_BOTTOM = 1.0 * inch
CARD_PAD = 0.3 * inch


def _hex(c: str) -> str:
    return c if c.startswith("#") else f"#{c}"


def _render_notes(c: canvas.Canvas, *, top: float, secondary: str) -> None:
    c.setStrokeColor(HexColor(secondary))
    line_y = top - 0.5 * inch
    while line_y >= CARD_BOTTOM + CARD_PAD:
        c.line(CARD_LEFT + CARD_PAD, line_y, CARD_RIGHT - CARD_PAD, line_y)
        line_y -= 0.35 * inch


def _render_checklist(c: canvas.Canvas, form, items: list[str], *, top: float, idx_prefix: str,
                       text_color: str, secondary: str) -> None:
    box = 0.22 * inch
    y = top - 0.5 * inch
    left = CARD_LEFT + CARD_PAD
    for i, item in enumerate(items):
        if y < CARD_BOTTOM + CARD_PAD:
            break
        draw_rounded_checkbox(c, form, name=f"{idx_prefix}_{i}", tooltip=item[:60],
                               cx=left + box/2, cy=y - box/2 + 2, size=box, accent_hex=secondary)
        c.setFillColor(HexColor(text_color))
        c.setFont(FONT_REGULAR, 11)
        c.drawString(left + box + 0.18 * inch, y - box + 4, item[:90])
        y -= 0.36 * inch


def _fit_text(c: canvas.Canvas, text: str, max_width: float, *, font_name: str, font_size: float) -> str:
    """Truncates with an ellipsis until the real rendered width (via
    stringWidth, not a guessed character count) fits the column -- a flat
    character limit overflowed into the next column whenever there were
    more than ~4 columns (found by actually rendering a real 6-column
    table and looking at it, not just generating it)."""
    if c.stringWidth(text, font_name, font_size) <= max_width:
        return text
    while text and c.stringWidth(text + "...", font_name, font_size) > max_width:
        text = text[:-1]
    return (text + "...") if text else ""


def _render_table(c: canvas.Canvas, columns: list[str], *, top: float, text_color: str, secondary: str) -> None:
    columns = columns[:6] or ["Item"]
    left, right = CARD_LEFT + CARD_PAD, CARD_RIGHT - CARD_PAD
    col_w = (right - left) / len(columns)
    header_h = 0.32 * inch
    row_h = 0.32 * inch
    table_top = top - 0.3 * inch
    rows = max(1, int((table_top - header_h - (CARD_BOTTOM + CARD_PAD)) // row_h))
    header_font_size = 9 if len(columns) <= 4 else 7.5
    header_pad = 0.08 * inch

    c.setFillColor(HexColor(secondary))
    c.roundRect(left, table_top - header_h, right - left, header_h, 6, fill=True, stroke=False)
    c.setFillColor(white)
    c.setFont(FONT_BOLD, header_font_size)
    for i, col in enumerate(columns):
        label = _fit_text(c, col.upper(), col_w - 2 * header_pad, font_name=FONT_BOLD, font_size=header_font_size)
        c.drawString(left + i * col_w + header_pad, table_top - header_h + 0.1 * inch, label)

    c.setStrokeColor(HexColor("#E6E6E6"))
    c.setLineWidth(1)
    grid_bottom = table_top - header_h - rows * row_h
    c.rect(left, grid_bottom, right - left, table_top - header_h - grid_bottom, fill=False, stroke=True)
    for i in range(1, len(columns)):
        x = left + i * col_w
        c.line(x, table_top - header_h, x, grid_bottom)
    y = table_top - header_h
    for _ in range(rows):
        c.line(left, y, right, y)
        y -= row_h


def _render_tracker(c: canvas.Canvas, form, *, top: float, periods: int, period_label: str, idx_prefix: str,
                     text_color: str, secondary: str) -> None:
    cols = 7
    rows = -(-periods // cols)
    left, right = CARD_LEFT + CARD_PAD, CARD_RIGHT - CARD_PAD
    cell_w = (right - left) / cols
    table_top = top - 0.3 * inch
    cell_h = min(0.75 * inch, (table_top - (CARD_BOTTOM + CARD_PAD)) / rows)
    n = 1
    for r in range(rows):
        for col in range(cols):
            if n > periods:
                break
            cx = left + col * cell_w
            cy = table_top - r * cell_h
            c.setFillColor(HexColor("#FAFAFA") if (r + col) % 2 == 0 else white)
            c.roundRect(cx + 2, cy - cell_h + 2, cell_w - 4, cell_h - 4, 6, fill=True, stroke=False)
            c.setFillColor(HexColor(text_color))
            c.setFont(FONT_BOLD, 9)
            c.drawString(cx + 0.08 * inch, cy - 0.18 * inch, f"{period_label} {n}")
            draw_rounded_checkbox(c, form, name=f"{idx_prefix}_{n}", tooltip=f"{period_label} {n}",
                                   cx=cx + cell_w - 0.22*inch, cy=cy - cell_h + 0.22*inch, size=0.24*inch,
                                   accent_hex=secondary)
            n += 1


def generate_pdf_product(path: Path, *, title: str, palette: dict, sections: list) -> None:
    register_fonts()
    primary = _hex(palette.get("primary", "#2EC4B6"))
    secondary = _hex(palette.get("secondary", "#F26B6B"))
    highlight = _hex(palette.get("highlight", "#FFC83D"))
    text_color = _hex(palette.get("text", "#1B4332"))

    c = canvas.Canvas(str(path), pagesize=LETTER)
    form = c.acroForm

    # --- Cover page ---
    c.setFillColor(HexColor(primary))
    c.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, fill=True, stroke=False)
    c.setFillColor(HexColor(secondary))
    c.rect(0, 0, PAGE_WIDTH, 0.15 * inch, fill=True, stroke=False)
    c.setFillColor(white)
    c.setFont(FONT_BOLD, 28 if len(title) < 32 else 22)
    c.drawCentredString(PAGE_WIDTH / 2, PAGE_HEIGHT / 2 + 14, title)
    c.setFont(FONT_REGULAR, 12)
    c.drawCentredString(PAGE_WIDTH / 2, PAGE_HEIGHT / 2 - 16, "Generated by Psalm 90:17 Commerce")
    c.showPage()

    # --- Content pages ---
    for idx, section in enumerate(sections):
        if isinstance(section, str):
            section = {"heading": section, "layout": "notes"}
        heading = section.get("heading", f"Section {idx + 1}")
        layout = section.get("layout", "notes")

        draw_page_background(c, palette=palette)
        content_top = draw_decorative_header(c, heading, "", palette=palette, seed=idx + 2)
        draw_rounded_card(c, left=CARD_LEFT, right=CARD_RIGHT, top=content_top - 0.2*inch, bottom=CARD_BOTTOM)
        card_top = content_top - 0.2 * inch

        if layout == "checklist" and section.get("items"):
            _render_checklist(c, form, section["items"], top=card_top, idx_prefix=f"chk{idx}",
                               text_color=text_color, secondary=secondary)
        elif layout == "table" and section.get("columns"):
            _render_table(c, section["columns"], top=card_top, text_color=text_color, secondary=secondary)
        elif layout == "tracker":
            _render_tracker(
                c, form, top=card_top, periods=section.get("periods", 31),
                period_label=section.get("period_label", "Day"), idx_prefix=f"trk{idx}",
                text_color=text_color, secondary=secondary,
            )
        else:
            _render_notes(c, top=card_top, secondary=secondary)
        c.showPage()

    c.save()


def generate_instructions_txt(path: Path, *, title: str) -> None:
    path.write_text(
        f"""{title} - Customer Instructions
=====================================

Thank you for your purchase!

1. Download the attached ZIP file and unzip it.
2. Open the PDF with any PDF reader (Adobe Acrobat, Preview, or your browser).
3. Print at 100% scale ("Actual Size") on US Letter (8.5x11in) paper for correct layout.
4. This is a digital product -- no physical item will be shipped.
5. For personal/non-commercial use. Contact the shop with any questions.
""",
        encoding="utf-8",
    )
