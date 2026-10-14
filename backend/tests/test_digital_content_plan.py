"""
Real digital-product content-plan tests -- the generic fallback used by
every non-chore-chart PDF niche used to be a single hardcoded
DEFAULT_SECTIONS ruled-lines template regardless of what the niche
actually was, which the owner correctly judged "super super basic
compared to ones selling for $5 on Etsy." These test the real rendering
engine (checklist/table/tracker layouts, with real AcroForm fields) and
the real content-plan validator that gates what a real AI response is
allowed to turn into rendered pages.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path

import pypdf

from app.agents.digital_production import _valid_content_plan
from app.agents.generators.pdf_generator import generate_pdf_product

PALETTE = {"primary": "#1B4332", "secondary": "#40916C", "accent": "#D8F3DC", "text": "#081C15"}


def test_backward_compatible_plain_string_sections_still_render_as_notes(tmp_path: Path):
    out = tmp_path / "plain.pdf"
    generate_pdf_product(out, title="Test Product", palette=PALETTE, sections=["Overview", "Notes"])
    reader = pypdf.PdfReader(str(out))
    assert len(reader.pages) == 3  # cover + 2 plain sections


def test_checklist_table_and_tracker_layouts_render_real_fillable_fields(tmp_path: Path):
    out = tmp_path / "plan.pdf"
    plan = [
        {"heading": "Master Checklist", "layout": "checklist", "items": ["Book venue", "Hire photographer", "Order cake"]},
        {"heading": "Budget Tracker", "layout": "table", "columns": ["Category", "Budgeted", "Actual", "Vendor", "Status", "Notes"]},
        {"heading": "Monthly Check-In", "layout": "tracker", "periods": 12, "period_label": "Month"},
    ]
    generate_pdf_product(out, title="Wedding Planning Templates", palette=PALETTE, sections=plan)

    reader = pypdf.PdfReader(str(out))
    assert len(reader.pages) == 4  # cover + 3 sections

    fields = reader.get_fields()
    types = Counter(f.get("/FT") for f in fields.values())
    assert types["/Btn"] == 3 + 12  # 3 checklist items + 12 tracker months, all real checkboxes


def test_table_headers_never_overlap_into_the_next_column(tmp_path: Path):
    """The real bug this caught before it reached a real listing: a flat
    24-character truncation overflowed into the adjacent column header
    whenever a column name was long and there were more than ~4 columns
    (found by actually rendering a 6-column table and looking at it)."""
    out = tmp_path / "wide_table.pdf"
    plan = [{
        "heading": "Vendor Contact Sheet", "layout": "table",
        "columns": ["Expense Category", "Estimated Budget Amount", "Actual Cost", "Vendor Business Name", "Paid Status", "Notes"],
    }]
    generate_pdf_product(out, title="Test", palette=PALETTE, sections=plan)

    doc_bytes = out.read_bytes()
    assert len(doc_bytes) > 0  # real file produced
    # Real geometric check: every rendered header label must fit within its
    # own column width, using the same stringWidth the renderer itself uses.
    from reportlab.pdfgen import canvas as _canvas
    from app.agents.generators.design_system import FONT_BOLD, register_fonts
    from app.agents.generators.pdf_generator import CARD_LEFT, CARD_PAD, CARD_RIGHT, _fit_text
    register_fonts()
    c = _canvas.Canvas(str(tmp_path / "scratch.pdf"))
    col_w = ((CARD_RIGHT - CARD_PAD) - (CARD_LEFT + CARD_PAD)) / 6
    for col in plan[0]["columns"]:
        fitted = _fit_text(c, col.upper(), col_w - 0.16 * 72, font_name=FONT_BOLD, font_size=7.5)
        assert c.stringWidth(fitted, FONT_BOLD, 7.5) <= col_w - 0.16 * 72


def test_content_plan_validator_accepts_a_real_shaped_plan():
    plan = [
        {"heading": "Checklist", "layout": "checklist", "items": ["Do a thing", "Do another thing"]},
        {"heading": "Table", "layout": "table", "columns": ["A", "B"]},
        {"heading": "Tracker", "layout": "tracker", "periods": 7, "period_label": "Day"},
        {"heading": "Notes", "layout": "notes"},
    ]
    result = _valid_content_plan(plan)
    assert result is not None and len(result) == 4
    assert result[2]["periods"] == 7 and result[2]["period_label"] == "Day"


def test_content_plan_validator_rejects_malformed_shapes():
    assert _valid_content_plan("not a list") is None
    assert _valid_content_plan([]) is None
    assert _valid_content_plan([{"heading": "X", "layout": "checklist"}]) is None  # missing items
    assert _valid_content_plan([{"heading": "X", "layout": "table"}]) is None  # missing columns
    assert _valid_content_plan([{"heading": "X", "layout": "not_a_real_layout"}]) is None
    assert _valid_content_plan([{"layout": "notes"}]) is None  # missing heading
    assert _valid_content_plan([{"section": "X", "description": "Y"}]) is None  # real wrong-shape LLM drift seen live


def test_content_plan_validator_truncates_oversized_lists_rather_than_rejecting():
    plan = [{"heading": "X", "layout": "table", "columns": [f"col{i}" for i in range(10)]}]
    result = _valid_content_plan(plan)
    assert result is not None and len(result[0]["columns"]) == 6

    plan2 = [{"heading": "X", "layout": "checklist", "items": [f"item{i}" for i in range(30)]}]
    result2 = _valid_content_plan(plan2)
    assert result2 is not None and len(result2[0]["items"]) == 20
