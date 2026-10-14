"""
Real POD artwork style-guidance tests -- built in direct response to the
owner's follow-up directive (2026-10-14): "we want the designs to be
close to the ones that are winning illustration wise." The real bug this
closes: _real_style_guidance() used to treat all 10 top-favorited
listings as equally informative when synthesizing a style pattern, which
would dilute a real standout's style with much-less-proven listings --
confirmed live for "Faith Cross Necklaces" (410/212 favorites for the top
two, then a steep drop to 19-51 for the rest of a real 10-result sample).
"""
from __future__ import annotations

from app.agents import pod_production as pp
from app.database import SessionLocal
from app.models.models import ProductSpecification


def _real_shaped_necklace_results():
    """Exact real response shape captured live (2026-10-14) for 'Faith
    Cross Necklaces' -- not a simplified stand-in."""
    return [
        {"title": "Sterling Silver Faith Cross Necklace & Earrings Set | Christian Jewelry for Women | Dainty Religious Gift | Minimalist Cross Jewelry",
         "tags": ["Faith Cross Necklace", "Religious Jewelry"], "num_favorers": 410},
        {"title": "Camargue Cross Pendant Necklace, 18K Gold Vermeil, Anchor Cross Necklace",
         "tags": ["Cross Pendant"], "num_favorers": 212},
        {"title": "Men's Necklace - Faith Cross Necklace - Stainless Steel Necklace",
         "tags": ["Mens Necklace"], "num_favorers": 51},
        {"title": "Dainty cross necklace, gold filled tiny cross pendant", "tags": [], "num_favorers": 43},
        {"title": "FAITH Cross necklace in 14k 18K SOLID Gold", "tags": [], "num_favorers": 34},
    ]


def test_style_guidance_samples_15_not_10(monkeypatch):
    """Widened from top_n=10 to top_n=15 (2026-10-14) to match
    market_intelligence.py's sample size and give the weighting more real
    data to work with."""
    db = SessionLocal()
    captured = {}

    def fake_search(keyword, *, access_token, sample_size, top_n):
        captured["top_n"] = top_n
        return _real_shaped_necklace_results()

    monkeypatch.setattr(pp, "search_top_listings", fake_search)
    monkeypatch.setattr(pp.oauth_store, "get_valid_etsy_token", lambda _db: "fake-token")
    monkeypatch.setattr(pp.settings, "etsy_api_key", "fake-key")
    monkeypatch.setattr(pp.settings, "etsy_api_secret", "fake-secret")
    monkeypatch.setattr(pp.settings, "etsy_shop_id", "fake-shop")

    product = ProductSpecification(title="Faith Cross Necklaces", format="necklace", product_type="pod",
                                    target_customer="x", problem_solved="x", design_brief={})
    pp._real_style_guidance(db, "pod_production", product)
    assert captured["top_n"] == 15
    db.close()


def test_style_guidance_prompt_includes_real_favorite_counts_and_weighting_instruction(monkeypatch):
    """The real fix: the AI must be given each listing's real favorite
    count (not just titles) and told to weight toward real standouts,
    not average flat across the whole sample."""
    db = SessionLocal()
    captured = {}

    monkeypatch.setattr(pp, "search_top_listings", lambda *a, **kw: _real_shaped_necklace_results())
    monkeypatch.setattr(pp.oauth_store, "get_valid_etsy_token", lambda _db: "fake-token")
    monkeypatch.setattr(pp.settings, "etsy_api_key", "fake-key")
    monkeypatch.setattr(pp.settings, "etsy_api_secret", "fake-secret")
    monkeypatch.setattr(pp.settings, "etsy_shop_id", "fake-shop")

    def fake_complete(db, *, agent_key, system_prompt, user_prompt, **kw):
        captured["system_prompt"] = system_prompt
        captured["user_prompt"] = user_prompt
        from app.integrations.ai_providers import AIResponse
        return AIResponse("Minimalist dainty cross silhouette.", "anthropic", "test-model", 10, 10, 0.001, False, {})

    monkeypatch.setattr(pp.ai_providers, "complete", fake_complete)

    product = ProductSpecification(title="Faith Cross Necklaces", format="necklace", product_type="pod",
                                    target_customer="x", problem_solved="x", design_brief={})
    guidance = pp._real_style_guidance(db, "pod_production", product)

    assert guidance == "Minimalist dainty cross silhouette."
    # Real favorite counts, not just titles, must reach the model.
    assert "410" in captured["user_prompt"] and "212" in captured["user_prompt"]
    # Explicit weighting instruction must be present, not a flat "find common patterns" ask.
    assert "standout" in captured["system_prompt"].lower()
    assert "weight" in captured["system_prompt"].lower()
    db.close()
