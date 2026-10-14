"""
Real visual design system tests -- built in direct response to the owner
comparing our chore chart to real top-selling Etsy listings: "how can we
charge when ours is plain jane." Checks the real shared assets
(font/icon files actually exist and the font actually loads in ReportLab)
and the real niche-aware palette selection, since every digital product
used to get the identical dark-green palette regardless of niche.
"""
from __future__ import annotations

from reportlab.pdfgen import canvas

from app.agents.creative_director import DIGITAL_PALETTE_THEMES, CreativeDirectorAgent, _digital_palette_for
from app.agents.generators import design_system
from app.database import SessionLocal
from app.models.models import ProductSpecification


def test_font_files_exist_and_are_properly_licensed():
    assert (design_system._FONTS_DIR / "Baloo2-Regular.ttf").exists()
    assert (design_system._FONTS_DIR / "Baloo2-Bold.ttf").exists()
    ofl = (design_system._FONTS_DIR / "Baloo2-OFL.txt").read_text(encoding="utf-8")
    assert "SIL Open Font License" in ofl


def test_fonts_register_and_actually_render_in_reportlab(tmp_path):
    design_system.register_fonts()  # must not raise, including when called a second time (idempotent)
    design_system.register_fonts()
    c = canvas.Canvas(str(tmp_path / "font_check.pdf"))
    c.setFont(design_system.FONT_BOLD, 24)
    width = c.stringWidth("Weekly Chore Chart", design_system.FONT_BOLD, 24)
    assert width > 0  # a real registered font reports real glyph widths


def test_all_nine_default_task_icons_exist_as_real_committed_assets():
    expected = [
        "make_bed", "brush_teeth", "get_dressed", "feed_pet", "tidy_bedroom",
        "homework", "put_away_toys", "help_dishes", "pack_school_bag",
    ]
    for name in expected:
        p = design_system.icon_path(name)
        assert p is not None and p.exists() and p.stat().st_size > 0


def test_unknown_icon_name_returns_none_not_an_error():
    assert design_system.icon_path("not_a_real_task") is None


def test_niche_palette_selection_matches_real_keywords():
    assert _digital_palette_for("Printable Chore Charts") == DIGITAL_PALETTE_THEMES["playful"]
    assert _digital_palette_for("Wedding Planning Templates") == DIGITAL_PALETTE_THEMES["elegant"]
    assert _digital_palette_for("Printable Budget Planners") == DIGITAL_PALETTE_THEMES["professional"]
    assert _digital_palette_for("Bible Verse Printable Wall Art") == DIGITAL_PALETTE_THEMES["faith"]
    assert _digital_palette_for("Something Entirely Unmatched") == DIGITAL_PALETTE_THEMES["default"]


def test_every_theme_has_the_full_palette_shape():
    required_keys = {"primary", "secondary", "accent", "highlight", "text"}
    for theme_name, palette in DIGITAL_PALETTE_THEMES.items():
        assert required_keys.issubset(palette.keys()), f"{theme_name} missing keys"
        for key, value in palette.items():
            assert value.startswith("#") and len(value) == 7, f"{theme_name}.{key} is not a real hex color"


def test_creative_director_agent_really_picks_a_niche_appropriate_palette():
    """Confirms the real agent (DB write included), not just the pure
    selection function, actually wires the themed palette through -- a
    kids' chore chart must no longer get the same dark-green palette as
    every other digital product used to."""
    db = SessionLocal()
    product = None
    try:
        product = ProductSpecification(
            title="Printable Chore Charts for Kids", product_type="digital", target_customer="x",
            problem_solved="x", format="pdf", design_brief={}, recommended_price_usd=5.0,
        )
        db.add(product)
        db.commit()
        db.refresh(product)

        brief = CreativeDirectorAgent(db).create_design_brief(product)
        assert brief["palette"] == DIGITAL_PALETTE_THEMES["playful"]
        db.refresh(product)
        assert product.design_brief["palette"] == DIGITAL_PALETTE_THEMES["playful"]
    finally:
        if product is not None:
            db.query(ProductSpecification).filter(ProductSpecification.id == product.id).delete()
            db.commit()
        db.close()
