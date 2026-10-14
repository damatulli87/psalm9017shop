"""
Real listing-hygiene test for the mangled-tag check, added alongside the
fix for a real bug found live (2026-10-14): a naive tag[:20] slice cut
Etsy tags mid-word and reached a real listing with tags like "chore chart
printabl" and a dangling trailing space ("kids responsibility "). This is
a deterministic, measurable fact ULTRON can check without any LLM call,
consistent with the rest of verify_listing_hygiene().
"""
from __future__ import annotations

from app.agents.ultron import FAIL, PASS, UltronSupervisorAgent
from app.database import SessionLocal
from app.models.models import MarketplaceListing, ProductSpecification


def _make_product_with_listing(db, *, tags: list[str]) -> ProductSpecification:
    product = ProductSpecification(
        title="Test Hygiene Product", product_type="digital", target_customer="x",
        problem_solved="x", format="pdf", design_brief={}, recommended_price_usd=5.0,
    )
    db.add(product)
    db.commit()
    db.refresh(product)
    listing = MarketplaceListing(
        product_id=product.id, storefront_channel="etsy", title="Test Hygiene Product",
        description="test", price_usd=5.0, tags=tags, status="draft", is_simulated=True,
    )
    db.add(listing)
    db.commit()
    return product


def test_mangled_tags_with_dangling_space_fail_hygiene_check():
    db = SessionLocal()
    product = None
    try:
        product = _make_product_with_listing(db, tags=["chore chart", "kids responsibility "])
        findings = UltronSupervisorAgent(db).verify_listing_hygiene(product)
        mangled = next(f for f in findings if f["check"] == "listing_hygiene_no_mangled_tags")
        assert mangled["status"] == FAIL
        assert "kids responsibility" in mangled["detail"]
    finally:
        if product is not None:
            db.query(MarketplaceListing).filter(MarketplaceListing.product_id == product.id).delete()
            db.query(ProductSpecification).filter(ProductSpecification.id == product.id).delete()
            db.commit()
        db.close()


def test_clean_tags_pass_hygiene_check():
    db = SessionLocal()
    product = None
    try:
        product = _make_product_with_listing(db, tags=["chore chart", "kids responsibility", "reward chart"])
        findings = UltronSupervisorAgent(db).verify_listing_hygiene(product)
        mangled = next(f for f in findings if f["check"] == "listing_hygiene_no_mangled_tags")
        assert mangled["status"] == PASS
    finally:
        if product is not None:
            db.query(MarketplaceListing).filter(MarketplaceListing.product_id == product.id).delete()
            db.query(ProductSpecification).filter(ProductSpecification.id == product.id).delete()
            db.commit()
        db.close()
