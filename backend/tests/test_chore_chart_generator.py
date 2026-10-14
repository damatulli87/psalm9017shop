"""
Real chore-chart bundle tests -- direct response to the owner's "super
super basic compared to ones selling for $5 on Etsy" feedback. Verifies
the actual rendered PDF, not just that generate_chore_chart_pdf() runs
without raising: real page count, real page dimensions, and the real
fillable AcroForm fields that respond to the #1 real competitive-research
signal found for this niche ("editable").
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path

import pypdf

from app.agents.generators.chore_chart_generator import generate_chore_chart_pdf

PALETTE = {"primary": "#1B4332", "secondary": "#40916C", "accent": "#D8F3DC", "text": "#081C15"}


def test_chore_chart_is_a_real_five_page_bundle_not_a_single_page(tmp_path: Path):
    out = tmp_path / "chore_chart.pdf"
    generate_chore_chart_pdf(out, title="Printable Chore Charts for Kids", palette=PALETTE)

    assert out.exists() and out.stat().st_size > 0
    reader = pypdf.PdfReader(str(out))
    assert len(reader.pages) == 5, "cover, instructions, weekly, monthly, reward/allowance"
    for page in reader.pages:
        box = page.mediabox
        assert (round(float(box.width)), round(float(box.height))) == (612, 792)  # real US Letter


def test_chore_chart_has_real_fillable_form_fields_not_just_drawn_boxes(tmp_path: Path):
    """The strongest real signal from live competitive research
    (search_top_listings against "Printable Chore Charts") was "editable"
    -- this asserts the chart actually responds to that with real AcroForm
    fields, not just visually-drawn rectangles a buyer can't interact with."""
    out = tmp_path / "chore_chart.pdf"
    generate_chore_chart_pdf(out, title="Printable Chore Charts for Kids", palette=PALETTE)

    reader = pypdf.PdfReader(str(out))
    fields = reader.get_fields()
    assert fields, "PDF must have real AcroForm fields, not just drawn rectangles"

    types = Counter(f.get("/FT") for f in fields.values())
    # 9 default tasks x 7 days (weekly) + 31 days (monthly) + 30 goals = 124 real checkboxes
    assert types["/Btn"] == 124
    # name, week-of, reward-earned, allowance-amount
    assert types["/Tx"] == 4
    for name in ("child_name", "week_of", "reward_earned", "allowance_amount"):
        assert name in fields


def test_chore_chart_respects_a_custom_task_list(tmp_path: Path):
    out = tmp_path / "chore_chart_custom.pdf"
    custom_tasks = ["Walk the dog", "Water plants"]
    generate_chore_chart_pdf(out, title="Custom Chart", palette=PALETTE, tasks=custom_tasks)

    reader = pypdf.PdfReader(str(out))
    fields = reader.get_fields()
    types = Counter(f.get("/FT") for f in fields.values())
    # 2 tasks x 7 days (weekly) + 31 (monthly) + 30 (goals) = 75
    assert types["/Btn"] == 75
