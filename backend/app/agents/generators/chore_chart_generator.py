"""
A genuine, niche-specific chore-chart layout -- not the generic ruled-lines
template. Built because the generic template was reviewed and correctly
judged not worth selling: this is an actual weekly task x day-of-week grid
with checkboxes, a name/week header, and a real reward tracker, which is
what a buyer expects from a printable kids' chore chart.
"""
from __future__ import annotations

from pathlib import Path

from reportlab.lib.pagesizes import LETTER
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

PAGE_WIDTH, PAGE_HEIGHT = LETTER

DEFAULT_TASKS = [
    "Make bed",
    "Brush teeth",
    "Get dressed",
    "Feed pet",
    "Tidy bedroom",
    "Homework",
    "Put away toys",
    "Help with dishes",
    "Pack school bag",
]
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _hex(c: str) -> str:
    return c if c.startswith("#") else f"#{c}"


def generate_chore_chart_pdf(path: Path, *, title: str, palette: dict, tasks: list[str] | None = None) -> None:
    tasks = tasks or DEFAULT_TASKS
    primary = _hex(palette.get("primary", "#1B4332"))
    secondary = _hex(palette.get("secondary", "#40916C"))
    accent = _hex(palette.get("accent", "#D8F3DC"))
    text_color = _hex(palette.get("text", "#081C15"))

    c = canvas.Canvas(str(path), pagesize=LETTER)

    # --- Cover page ---
    c.setFillColor(primary)
    c.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, fill=True, stroke=False)
    c.setFillColor(accent)
    c.setFont("Helvetica-Bold", 30)
    c.drawCentredString(PAGE_WIDTH / 2, PAGE_HEIGHT / 2 + 14, title)
    c.setFont("Helvetica", 13)
    c.drawCentredString(PAGE_WIDTH / 2, PAGE_HEIGHT / 2 - 16, "A weekly chore chart for kids")
    c.showPage()

    # --- Chart page ---
    c.setFillColor("#FFFFFF")
    c.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, fill=True, stroke=False)

    c.setFillColor(text_color)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(0.75 * inch, PAGE_HEIGHT - 0.9 * inch, title)

    c.setFont("Helvetica", 11)
    c.drawString(0.75 * inch, PAGE_HEIGHT - 1.25 * inch, "Name: " + "_" * 28)
    c.drawString(5.1 * inch, PAGE_HEIGHT - 1.25 * inch, "Week of: " + "_" * 14)

    grid_left = 0.75 * inch
    grid_right = PAGE_WIDTH - 0.75 * inch
    grid_top = PAGE_HEIGHT - 1.65 * inch
    task_col_w = 1.9 * inch
    day_col_w = (grid_right - grid_left - task_col_w) / len(DAYS)
    header_h = 0.36 * inch
    row_h = 0.42 * inch
    box_size = 0.2 * inch

    # Header row
    c.setFillColor(secondary)
    c.rect(grid_left, grid_top - header_h, grid_right - grid_left, header_h, fill=True, stroke=False)
    c.setFillColor("#FFFFFF")
    c.setFont("Helvetica-Bold", 9)
    c.drawString(grid_left + 0.1 * inch, grid_top - header_h + 0.12 * inch, "TASK")
    for i, day in enumerate(DAYS):
        cx = grid_left + task_col_w + i * day_col_w + day_col_w / 2
        c.drawCentredString(cx, grid_top - header_h + 0.12 * inch, day.upper())

    # Task rows: alternating shading, a checkbox per day, row + column grid lines
    c.setFont("Helvetica", 10)
    row_top = grid_top - header_h
    for idx, task in enumerate(tasks):
        row_bottom = row_top - row_h
        if idx % 2 == 1:
            c.setFillColor(accent)
            c.rect(grid_left, row_bottom, grid_right - grid_left, row_h, fill=True, stroke=False)
        c.setFillColor(text_color)
        c.drawString(grid_left + 0.1 * inch, row_bottom + row_h / 2 - 4, task)

        c.setStrokeColor(secondary)
        c.setLineWidth(1)
        for i in range(len(DAYS)):
            cx = grid_left + task_col_w + i * day_col_w + day_col_w / 2
            cy = row_bottom + row_h / 2
            c.rect(cx - box_size / 2, cy - box_size / 2, box_size, box_size, fill=False, stroke=True)
        row_top = row_bottom

    grid_bottom = row_top

    # Outer border + column separators for the whole grid (header + rows)
    c.setStrokeColor(secondary)
    c.setLineWidth(1.2)
    c.rect(grid_left, grid_bottom, grid_right - grid_left, (grid_top - grid_bottom), fill=False, stroke=True)
    c.line(grid_left + task_col_w, grid_top, grid_left + task_col_w, grid_bottom)
    for i in range(1, len(DAYS)):
        x = grid_left + task_col_w + i * day_col_w
        c.line(x, grid_top, x, grid_bottom)
    # row separators
    y = grid_top - header_h
    for _ in tasks:
        c.line(grid_left, y, grid_right, y)
        y -= row_h

    # --- Reward tracker footer ---
    footer_y = grid_bottom - 0.5 * inch
    c.setFillColor(text_color)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(grid_left, footer_y, "Weekly reward:")
    c.setFont("Helvetica", 10)
    c.drawString(grid_left, footer_y - 0.22 * inch, "Checked boxes this week: _____ out of " + str(len(tasks) * 7))
    c.drawString(grid_left, footer_y - 0.44 * inch, "Reward earned: " + "_" * 40)

    c.setFont("Helvetica", 8)
    c.setFillColor(secondary)
    c.drawString(grid_left, 0.6 * inch, "Check off each task as it's completed. Print one page per week.")

    c.showPage()
    c.save()
