"""
A genuine, niche-specific chore-chart BUNDLE with real visual design, not
a plain data table.

Two real gaps closed, in direct response to two rounds of owner feedback:

  1. "super super basic compared to ones selling for $5 on Etsy" -- fixed
     by going from a 1-page cover+grid to a real 5-page bundle grounded in
     real competitive research (see module history / PROGRESS.md): cover,
     instructions, weekly chart, monthly overview, reward+allowance
     tracker, all as REAL fillable AcroForm fields.
  2. "how can we charge when ours is plain jane" -- the structural fix
     above was still rendered in plain Helvetica on a flat white page,
     visibly worse than real competing listings (actual icon
     illustrations, playful rounded typography, colorful decorative
     treatment). Fixed using design_system.py: a real embedded font
     (Baloo 2), a decorative two-tone header with confetti dots, a white
     rounded content card over a tinted page background, and real
     AI-generated icon illustrations per default task (generated once,
     committed as static assets under assets/icons/ -- never regenerated
     per pipeline run, so this costs nothing per sale).
"""
from __future__ import annotations

import random
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
    draw_icon_badge,
    draw_page_background,
    draw_rounded_card,
    draw_rounded_checkbox,
    icon_path,
    register_fonts,
)

# (task label, icon asset name) -- icon asset name maps to a real committed
# PNG under assets/icons/; a task with no matching asset just gets a plain
# color badge (see design_system.draw_icon_badge), never a crash.
DEFAULT_TASKS = [
    ("Make bed", "make_bed"),
    ("Brush teeth", "brush_teeth"),
    ("Get dressed", "get_dressed"),
    ("Feed pet", "feed_pet"),
    ("Tidy bedroom", "tidy_bedroom"),
    ("Homework", "homework"),
    ("Put away toys", "put_away_toys"),
    ("Help with dishes", "help_dishes"),
    ("Pack school bag", "pack_school_bag"),
]
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _hex(c: str) -> str:
    return c if c.startswith("#") else f"#{c}"


def generate_chore_chart_pdf(path: Path, *, title: str, palette: dict, tasks: list[str] | None = None) -> None:
    register_fonts()
    primary = _hex(palette.get("primary", "#2EC4B6"))
    secondary = _hex(palette.get("secondary", "#F26B6B"))
    highlight_hex = _hex(palette.get("highlight", "#FFC83D"))
    text_color = HexColor(_hex(palette.get("text", "#1B4332")))
    secondary_color = HexColor(secondary)
    badge_cycle = [secondary, primary, highlight_hex]

    # A caller-supplied custom task list has no known icon mapping -- falls
    # back to a plain color badge per task (still on-brand, just no image).
    task_rows: list[tuple[str, Path | None]] = (
        [(t, None) for t in tasks] if tasks else [(label, icon_path(asset)) for label, asset in DEFAULT_TASKS]
    )

    c = canvas.Canvas(str(path), pagesize=LETTER)
    form = c.acroForm

    # --- Page 1: Cover (its own layout, not draw_decorative_header --
    # that function sizes/positions its title for a short header band, not
    # a full-page cover; reusing it here previously made the title and
    # subtitles overlap into an illegible stack, caught by actually
    # rendering the page and looking at it) ---
    draw_page_background(c, palette=palette)
    c.setFillColor(HexColor(primary))
    c.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, fill=True, stroke=False)
    c.setFillColor(HexColor(secondary))
    c.rect(0, 0, PAGE_WIDTH, 0.15 * inch, fill=True, stroke=False)

    rng = random.Random(1)
    dot_colors = [HexColor(secondary), HexColor(highlight_hex), white]
    clear_top, clear_bottom = PAGE_HEIGHT * 0.38, PAGE_HEIGHT * 0.62
    for _ in range(26):
        x = rng.uniform(0.3 * inch, PAGE_WIDTH - 0.3 * inch)
        y = rng.uniform(0.3 * inch, PAGE_HEIGHT - 0.3 * inch)
        if clear_bottom > y > clear_top:
            continue
        r = rng.uniform(0.03 * inch, 0.07 * inch)
        c.setFillColor(rng.choice(dot_colors))
        c.circle(x, y, r, fill=True, stroke=False)

    c.setFillColor(white)
    c.setFont(FONT_BOLD, 30 if len(title) < 32 else 24)
    c.drawCentredString(PAGE_WIDTH / 2, PAGE_HEIGHT / 2 + 14, title)
    c.setFont(FONT_REGULAR, 13)
    c.drawCentredString(PAGE_WIDTH / 2, PAGE_HEIGHT / 2 - 20, "A printable AND fillable weekly chore chart bundle")
    c.setFont(FONT_REGULAR, 9.5)
    c.drawCentredString(PAGE_WIDTH / 2, PAGE_HEIGHT / 2 - 42, "Weekly chart - Monthly tracker - Reward & allowance tracker")
    c.showPage()

    # --- Page 2: Instructions ---
    draw_page_background(c, palette=palette)
    content_top = draw_decorative_header(c, "How to use this chart", "Both a print-and-check chart and a fillable PDF form", palette=palette)
    draw_rounded_card(c, left=0.6*inch, right=PAGE_WIDTH-0.6*inch, top=content_top-0.2*inch, bottom=1.0*inch)
    y = content_top - 0.6*inch
    instructions = [
        "This bundle works two ways -- pick whichever is easier for your family:",
        "",
        "1. PRINT IT: Print any page and check off boxes by hand with a pen or marker.",
        "   Printing one weekly chart per week works well on a fridge or wall.",
        "",
        "2. FILL IT IN DIGITALLY: Open this PDF in Adobe Acrobat Reader (free) or another",
        "   PDF app that supports fillable forms. Click any box to check it off, and click",
        "   the Name/Week fields to type directly into the chart -- no printing needed.",
        "",
        "What's included in this bundle:",
        "  - Page 3: Weekly chore chart (7 days x your task list)",
        "  - Page 4: Monthly overview -- a full month at a glance for daily routines",
        "  - Page 5: Reward & allowance tracker",
        "",
        "Tip: laminate a printed copy and use a dry-erase marker to reuse it every week.",
    ]
    c.setFont(FONT_REGULAR, 10.5)
    for line in instructions:
        c.setFillColor(text_color)
        c.drawString(0.9 * inch, y, line)
        y -= 0.26 * inch
    c.showPage()

    # --- Page 3: Weekly chore chart (real fillable form, real icons) ---
    draw_page_background(c, palette=palette)
    content_top = draw_decorative_header(c, title, "Weekly chart", palette=palette)
    card_left, card_right = 0.6*inch, PAGE_WIDTH - 0.6*inch
    card_top = content_top - 0.2*inch
    card_bottom = 1.0 * inch
    draw_rounded_card(c, left=card_left, right=card_right, top=card_top, bottom=card_bottom)

    c.setFont(FONT_BOLD, 12)
    c.setFillColor(text_color)
    c.drawString(card_left + 0.3*inch, card_top - 0.5*inch, "Name:")
    form.textfield(name="child_name", tooltip="Child's name", x=card_left + 1.0*inch, y=card_top - 0.58*inch,
                    width=2.3*inch, height=0.26*inch, borderStyle="underlined", borderColor=secondary_color,
                    fillColor=white, forceBorder=True)
    c.drawString(card_left + 3.7*inch, card_top - 0.5*inch, "Week of:")
    form.textfield(name="week_of", tooltip="Week of", x=card_left + 4.75*inch, y=card_top - 0.58*inch,
                    width=1.4*inch, height=0.26*inch, borderStyle="underlined", borderColor=secondary_color,
                    fillColor=white, forceBorder=True)

    icon_badge = 0.5 * inch
    task_col_w = 2.3 * inch
    row_h = (card_top - 0.95*inch - (card_bottom + 0.4*inch)) / len(task_rows)
    row_h = min(row_h, 0.62 * inch)
    row_top = card_top - 0.95*inch
    day_zone_left = card_left + 0.3*inch + icon_badge + 0.25*inch + task_col_w
    day_col_w = (card_right - 0.3*inch - day_zone_left) / len(DAYS)

    c.setFont(FONT_BOLD, 9)
    c.setFillColor(text_color)
    for d, day in enumerate(DAYS):
        cx = day_zone_left + d*day_col_w + day_col_w/2
        c.drawCentredString(cx, row_top + 0.12*inch, day[:1])

    for i, (task, icon_file) in enumerate(task_rows):
        ry = row_top - i * row_h
        badge_x = card_left + 0.3*inch
        badge_y = ry - icon_badge + (row_h - icon_badge) / 2
        accent = badge_cycle[i % len(badge_cycle)]
        draw_icon_badge(c, icon_file=icon_file, x=badge_x, y=badge_y, size=icon_badge, accent_hex=accent)

        c.setFillColor(text_color)
        c.setFont(FONT_BOLD, 11.5)
        c.drawString(badge_x + icon_badge + 0.25*inch, ry - row_h/2 + 0.1*inch, task[:28])

        for d in range(len(DAYS)):
            cx = day_zone_left + d*day_col_w + day_col_w/2
            cy = ry - row_h/2 + 0.1*inch
            draw_rounded_checkbox(c, form, name=f"wk_{i}_{d}", tooltip=f"{task} - {DAYS[d]}",
                                   cx=cx, cy=cy, size=0.26*inch, accent_hex=secondary)

    c.setFont(FONT_REGULAR, 8)
    c.setFillColor(HexColor(secondary))
    c.drawString(card_left + 0.3*inch, card_bottom - 0.3*inch,
                 "Check off each task as it's completed -- print one page per week, or fill in digitally.")
    c.showPage()

    # --- Page 4: Monthly overview ---
    draw_page_background(c, palette=palette)
    content_top = draw_decorative_header(c, title, "Monthly overview -- check off each day the routine was completed", palette=palette)
    card_left, card_right = 0.6*inch, PAGE_WIDTH - 0.6*inch
    card_top = content_top - 0.2*inch
    card_bottom = 1.0 * inch
    draw_rounded_card(c, left=card_left, right=card_right, top=card_top, bottom=card_bottom)

    cols, rows = 7, 5
    grid_left, grid_right = card_left + 0.3*inch, card_right - 0.3*inch
    cell_w = (grid_right - grid_left) / cols
    cell_h = 0.75 * inch
    month_top = card_top - 0.4*inch
    day_num = 1
    for r in range(rows):
        for col in range(cols):
            if day_num > 31:
                break
            cx = grid_left + col * cell_w
            cy = month_top - r * cell_h
            c.setFillColor(HexColor("#FAFAFA") if (r + col) % 2 == 0 else white)
            c.roundRect(cx + 2, cy - cell_h + 2, cell_w - 4, cell_h - 4, 6, fill=True, stroke=False)
            c.setFillColor(text_color)
            c.setFont(FONT_BOLD, 9)
            c.drawString(cx + 0.08*inch, cy - 0.18*inch, str(day_num))
            draw_rounded_checkbox(c, form, name=f"month_day_{day_num}", tooltip=f"Day {day_num}",
                                   cx=cx + cell_w - 0.22*inch, cy=cy - cell_h + 0.22*inch, size=0.24*inch,
                                   accent_hex=secondary)
            day_num += 1

    c.setFont(FONT_REGULAR, 8)
    c.setFillColor(HexColor(secondary))
    c.drawString(card_left + 0.3*inch, card_bottom - 0.3*inch,
                 "Covers any month (up to 31 days) -- leave extra boxes blank for shorter months.")
    c.showPage()

    # --- Page 5: Reward + allowance tracker ---
    draw_page_background(c, palette=palette)
    content_top = draw_decorative_header(c, title, "Reward & allowance tracker", palette=palette)
    card_left, card_right = 0.6*inch, PAGE_WIDTH - 0.6*inch
    card_top = content_top - 0.2*inch
    card_bottom = 1.0 * inch
    draw_rounded_card(c, left=card_left, right=card_right, top=card_top, bottom=card_bottom)

    y = card_top - 0.45*inch
    c.setFillColor(text_color)
    c.setFont(FONT_BOLD, 14)
    c.drawString(card_left + 0.3*inch, y, "Goal tracker")
    c.setFont(FONT_REGULAR, 9.5)
    c.setFillColor(HexColor(secondary))
    c.drawString(card_left + 0.3*inch, y - 0.22*inch, "Check one box for each completed goal, working toward the reward below.")

    goal_top = y - 0.6*inch
    per_row = 10
    goal_count = 30
    star_size = 0.28 * inch
    row_step = star_size + 0.18 * inch
    gap = (card_right - card_left - 0.6*inch - per_row * star_size) / (per_row - 1)
    goal_rows = -(-goal_count // per_row)
    for i in range(goal_count):
        row = i // per_row
        col = i % per_row
        cx = card_left + 0.3*inch + col * (star_size + gap) + star_size/2
        cy = goal_top - row * row_step
        draw_rounded_checkbox(c, form, name=f"goal_{i}", tooltip=f"Goal {i + 1}", cx=cx, cy=cy,
                               size=star_size, accent_hex=[secondary, primary, highlight_hex][row % 3])

    goal_grid_bottom = goal_top - (goal_rows - 1) * row_step - star_size / 2
    tracker_y = goal_grid_bottom - 0.5*inch
    c.setFillColor(text_color)
    c.setFont(FONT_BOLD, 13)
    c.drawString(card_left + 0.3*inch, tracker_y, "Reward earned")
    c.setFont(FONT_REGULAR, 11)
    c.drawString(card_left + 0.3*inch, tracker_y - 0.3*inch, "Reward:")
    form.textfield(name="reward_earned", tooltip="Reward earned", x=card_left + 1.15*inch, y=tracker_y - 0.34*inch,
                    width=card_right - card_left - 1.45*inch, height=0.24*inch, borderStyle="underlined",
                    borderColor=secondary_color, fillColor=white, forceBorder=True)

    c.setFont(FONT_BOLD, 13)
    c.drawString(card_left + 0.3*inch, tracker_y - 0.72*inch, "Allowance")
    c.setFont(FONT_REGULAR, 11)
    c.drawString(card_left + 0.3*inch, tracker_y - 1.02*inch, "Amount earned this week: $")
    form.textfield(name="allowance_amount", tooltip="Allowance amount", x=card_left + 2.55*inch, y=tracker_y - 1.06*inch,
                    width=1.2*inch, height=0.24*inch, borderStyle="underlined", borderColor=secondary_color,
                    fillColor=white, forceBorder=True)

    c.setFont(FONT_REGULAR, 8)
    c.setFillColor(HexColor(secondary))
    c.drawString(card_left + 0.3*inch, card_bottom - 0.3*inch, "Fill in digitally, or print and use a sticker on each goal box.")
    c.showPage()

    c.save()
