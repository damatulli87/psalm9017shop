"""
Real "what's actually winning" market-signal tests -- built in direct
response to the owner's course-correction (2026-10-14): "why are we
looking at saturation? we need to be looking at what is selling... chase
what design and product is selling the most and piggy back off of that."
Etsy's real API has no sales/units-sold field for listings we don't own,
so real favorites (num_favorers) concentration among the top real results
is the real proxy used: a clear standout is treated as evidence of a
proven approach to learn from, not a saturation risk to avoid (the
opposite interpretation of the same underlying ratio).
"""
from __future__ import annotations

from app.agents.market_intelligence import MarketIntelligenceAgent, _standout_score_from_ratio
from app.agents.opportunity_engine import DEFAULT_WEIGHTS, OpportunityDecisionEngine
from app.database import SessionLocal
from app.models.models import MarketOpportunity, OpportunityScore, ResearchSource


def test_standout_score_rewards_a_clear_real_standout():
    """A flat field (no real standout) scores LOWER than a clear real
    standout -- the opposite of how this ratio would read as a saturation/
    entrenchment risk. Confirmed against the real chore-chart data found
    live (2026-10-14): ratio 9.57 (220 favorites vs. 23 median) should
    land in the "clear standout" band, not be penalized."""
    assert _standout_score_from_ratio(1.2) < _standout_score_from_ratio(9.57)
    assert _standout_score_from_ratio(9.57) == 0.85
    assert _standout_score_from_ratio(1.2) == 0.40


def test_standout_score_extreme_outlier_scores_slightly_lower_than_clear_standout():
    """A single freak-outlier ratio (>15x) is still real evidence, but
    less reliable than a clear-but-moderate lead -- scores high but not
    the highest band."""
    clear = _standout_score_from_ratio(10.0)
    extreme = _standout_score_from_ratio(50.0)
    assert extreme < clear
    assert extreme > _standout_score_from_ratio(1.0)


def test_get_market_signal_computes_real_standout_from_live_shaped_data(monkeypatch):
    """Monkeypatches search_top_listings to the exact real response shape
    captured live for 'Printable Chore Charts' (2026-10-14) -- not a
    simplified stand-in -- and confirms the real computation matches what
    was actually observed live."""
    db = SessionLocal()
    try:
        real_favorites = [220, 54, 44, 43, 36, 30, 23, 23, 23, 21, 17, 4, 4, 2, 2]
        fake_top = [
            {"title": "Editable Cleaning Cards, Printable Chore Chart, ADHD Cleaning Checklist, Room by Room Family Organizer",
             "tags": ["Cleaning Cards", "Chore Chart", "ADHD Checklist"], "num_favorers": real_favorites[0]},
        ] + [{"title": f"Other listing {i}", "tags": [], "num_favorers": f} for i, f in enumerate(real_favorites[1:])]

        import app.agents.market_intelligence as mi
        monkeypatch.setattr(mi, "search_top_listings", lambda keyword, **kw: fake_top)
        monkeypatch.setattr(mi.oauth_store, "get_valid_etsy_token", lambda _db: "fake-token")
        # etsy_configured is a read-only computed property (no setter) --
        # patch the real underlying fields it derives from instead (same
        # gotcha hit and fixed earlier this session in test_order_fulfillment.py).
        monkeypatch.setattr(mi.settings, "etsy_api_key", "fake-key")
        monkeypatch.setattr(mi.settings, "etsy_api_secret", "fake-secret")
        monkeypatch.setattr(mi.settings, "etsy_shop_id", "fake-shop")

        agent = MarketIntelligenceAgent(db)
        signal, is_real = agent._get_market_signal("Printable Chore Charts -- test keyword")
        assert is_real
        assert signal["standout_ratio"] == 9.57
        assert signal["standout_score"] == 0.85
        assert signal["top_listing_favorites"] == 220
        assert "ADHD" in signal["top_listing_title"]
    finally:
        db.query(ResearchSource).filter(ResearchSource.name == "Market signal: Printable Chore Charts -- test keyword").delete()
        db.commit()
        db.close()


def test_get_market_signal_returns_none_when_etsy_not_connected(monkeypatch):
    db = SessionLocal()
    try:
        import app.agents.market_intelligence as mi
        # etsy_configured is read-only, derived from these three real
        # fields -- clear one to make it naturally evaluate False.
        monkeypatch.setattr(mi.settings, "etsy_api_key", None)
        agent = MarketIntelligenceAgent(db)
        signal, is_real = agent._get_market_signal("some keyword never cached before xyz123")
        assert signal is None and is_real is False
    finally:
        db.close()


def test_opportunity_scoring_uses_real_market_signal_not_flat_placeholder():
    """The real bug this replaces: differentiation_score used to be a flat
    0.50 for every single opportunity regardless of real conditions. Two
    real different market_signal inputs must now produce two different
    real differentiation_scores."""
    db = SessionLocal()
    opp_standout = opp_flat = None
    try:
        opp_standout = MarketOpportunity(
            niche_title="Test Niche Standout", category="digital", description="test",
            evidence_summary={
                "is_real_data": True, "average_interest_0_100": 40,
                "etsy_listing_count": 10000, "etsy_competition_is_real": True,
                "market_signal": {
                    "standout_ratio": 9.57, "standout_score": 0.85, "top_listing_title": "x",
                    "top_listing_tags": [], "top_listing_favorites": 220, "median_favorites": 23, "sample_size": 15,
                },
                "market_signal_is_real": True,
            },
        )
        opp_flat = MarketOpportunity(
            niche_title="Test Niche Flat", category="digital", description="test",
            evidence_summary={
                "is_real_data": True, "average_interest_0_100": 40,
                "etsy_listing_count": 10000, "etsy_competition_is_real": True,
                "market_signal": {
                    "standout_ratio": 1.3, "standout_score": 0.40, "top_listing_title": "y",
                    "top_listing_tags": [], "top_listing_favorites": 30, "median_favorites": 23, "sample_size": 15,
                },
                "market_signal_is_real": True,
            },
        )
        db.add(opp_standout)
        db.add(opp_flat)
        db.commit()
        db.refresh(opp_standout)
        db.refresh(opp_flat)

        engine = OpportunityDecisionEngine(db)
        score_standout = engine.score_opportunity(opp_standout)
        score_flat = engine.score_opportunity(opp_flat)

        assert score_standout.differentiation_score == 0.85
        assert score_flat.differentiation_score == 0.40
        assert score_standout.weighted_total > score_flat.weighted_total
    finally:
        for opp in (opp_standout, opp_flat):
            if opp is not None:
                db.query(OpportunityScore).filter(OpportunityScore.opportunity_id == opp.id).delete()
                db.query(MarketOpportunity).filter(MarketOpportunity.id == opp.id).delete()
        db.commit()
        db.close()


def test_differentiation_potential_weight_raised_above_competitive_opportunity():
    """2026-10-14 owner directive: proof of what's selling should carry
    more real weight than raw listing-count saturation."""
    assert DEFAULT_WEIGHTS["differentiation_potential"] > DEFAULT_WEIGHTS["competitive_opportunity"]
    assert sum(DEFAULT_WEIGHTS.values()) == 1.0
