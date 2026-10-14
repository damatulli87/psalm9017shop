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
"""
from __future__ import annotations

from pathlib import Path

from reportlab.lib.colors import HexColor, white
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

PAGE_WIDTH, PAGE_HEIGHT = LETTER  # 612 x 792 points = 8.5x11in, standard US Letter printable

CONTENT_TOP = PAGE_HEIGHT - 1.5 * inch
CONTENT_LEFT = 0.75 * inch
CONTENT_RIGHT = PAGE_WIDTH - 0.75 * inch
CONTENT_BOTTOM = 0.75 * inch


def _hex(c: str) -> str:
    return c if c.startswith("#") else f"#{c}"


def _section_heading(c: canvas.Canvas, heading: str, *, text_color: str) -> None:
    c.setFillColor("#FFFFFF")
    c.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, fill=True, stroke=False)
    c.setFillColor(text_color)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(CONTENT_LEFT, PAGE_HEIGHT - 1 * inch, heading)


def _render_notes(c: canvas.Canvas, *, secondary: str) -> None:
    c.setStrokeColor(secondary)
    line_y = CONTENT_TOP
    while line_y >= CONTENT_BOTTOM:
        c.line(CONTENT_LEFT, line_y, CONTENT_RIGHT, line_y)
        line_y -= 0.35 * inch


def _render_checklist(c: canvas.Canvas, form, items: list[str], *, idx_prefix: str,
                       text_color: str, secondary_color) -> None:
    box = 0.18 * inch
    y = CONTENT_TOP
    for i, item in enumerate(items):
        if y < CONTENT_BOTTOM:
            break
        form.checkbox(
            name=f"{idx_prefix}_{i}", tooltip=item[:60],
            x=CONTENT_LEFT, y=y - box, size=box,
            borderColor=secondary_color, fillColor=white, checked=False, relative=False,
        )
        c.setFillColor(text_color)
        c.setFont("Helvetica", 11)
        c.drawString(CONTENT_LEFT + box + 0.15 * inch, y - box + 2, item[:90])
        y -= 0.34 * inch


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


def _render_table(c: canvas.Canvas, columns: list[str], *, text_color: str, secondary: str) -> None:
    columns = columns[:6] or ["Item"]
    col_w = (CONTENT_RIGHT - CONTENT_LEFT) / len(columns)
    header_h = 0.3 * inch
    row_h = 0.32 * inch
    rows = max(1, int((CONTENT_TOP - CONTENT_BOTTOM - header_h) // row_h))
    header_font_size = 9 if len(columns) <= 4 else 7.5
    header_pad = 0.08 * inch

    c.setFillColor(secondary)
    c.rect(CONTENT_LEFT, CONTENT_TOP - header_h, CONTENT_RIGHT - CONTENT_LEFT, header_h, fill=True, stroke=False)
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", header_font_size)
    for i, col in enumerate(columns):
        label = _fit_text(c, col.upper(), col_w - 2 * header_pad, font_name="Helvetica-Bold", font_size=header_font_size)
        c.drawString(CONTENT_LEFT + i * col_w + header_pad, CONTENT_TOP - header_h + 0.1 * inch, label)

    c.setStrokeColor(secondary)
    c.setLineWidth(1)
    grid_bottom = CONTENT_TOP - header_h - rows * row_h
    c.rect(CONTENT_LEFT, grid_bottom, CONTENT_RIGHT - CONTENT_LEFT, CONTENT_TOP - header_h - grid_bottom, fill=False, stroke=True)
    for i in range(1, len(columns)):
        x = CONTENT_LEFT + i * col_w
        c.line(x, CONTENT_TOP - header_h, x, grid_bottom)
    y = CONTENT_TOP - header_h
    for _ in range(rows):
        c.line(CONTENT_LEFT, y, CONTENT_RIGHT, y)
        y -= row_h


def _render_tracker(c: canvas.Canvas, form, *, periods: int, period_label: str, idx_prefix: str,
                     text_color: str, secondary: str, secondary_color) -> None:
    cols = 7
    rows = -(-periods // cols)
    cell_w = (CONTENT_RIGHT - CONTENT_LEFT) / cols
    cell_h = min(0.75 * inch, (CONTENT_TOP - CONTENT_BOTTOM) / rows)
    n = 1
    for r in range(rows):
        for col in range(cols):
            if n > periods:
                break
            cx = CONTENT_LEFT + col * cell_w
            cy = CONTENT_TOP - r * cell_h
            c.setStrokeColor(secondary)
            c.setLineWidth(1)
            c.rect(cx, cy - cell_h, cell_w, cell_h, fill=False, stroke=True)
            c.setFillColor(text_color)
            c.setFont("Helvetica", 9)
            c.drawString(cx + 0.06 * inch, cy - 0.16 * inch, f"{period_label} {n}")
            form.checkbox(
                name=f"{idx_prefix}_{n}", tooltip=f"{period_label} {n}",
                x=cx + cell_w - 0.3 * inch, y=cy - cell_h + 0.1 * inch, size=0.2 * inch,
                borderColor=secondary_color, fillColor=white, checked=False, relative=False,
            )
            n += 1


def generate_pdf_product(path: Path, *, title: str, palette: dict, sections: list) -> None:
    primary = _hex(palette.get("primary", "#1B4332"))
    secondary = _hex(palette.get("secondary", "#40916C"))
    accent = _hex(palette.get("accent", "#D8F3DC"))
    text_color = _hex(palette.get("text", "#081C15"))
    secondary_color = HexColor(secondary)

    c = canvas.Canvas(str(path), pagesize=LETTER)
    form = c.acroForm

    # --- Cover page ---
    c.setFillColor(primary)
    c.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, fill=True, stroke=False)
    c.setFillColor(accent)
    c.setFont("Helvetica-Bold", 28)
    c.drawCentredString(PAGE_WIDTH / 2, PAGE_HEIGHT / 2 + 20, title)
    c.setFont("Helvetica", 12)
    c.drawCentredString(PAGE_WIDTH / 2, PAGE_HEIGHT / 2 - 10, "Generated by Psalm 90:17 Commerce")
    c.showPage()

    # --- Content pages ---
    for idx, section in enumerate(sections):
        if isinstance(section, str):
            section = {"heading": section, "layout": "notes"}
        heading = section.get("heading", f"Section {idx + 1}")
        layout = section.get("layout", "notes")

        _section_heading(c, heading, text_color=text_color)
        if layout == "checklist" and section.get("items"):
            _render_checklist(c, form, section["items"], idx_prefix=f"chk{idx}",
                               text_color=text_color, secondary_color=secondary_color)
        elif layout == "table" and section.get("columns"):
            _render_table(c, section["columns"], text_color=text_color, secondary=secondary)
        elif layout == "tracker":
            _render_tracker(
                c, form, periods=section.get("periods", 31), period_label=section.get("period_label", "Day"),
                idx_prefix=f"trk{idx}", text_color=text_color, secondary=secondary, secondary_color=secondary_color,
            )
        else:
            _render_notes(c, secondary=secondary)
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
