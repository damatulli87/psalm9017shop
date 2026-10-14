"""
Product Opportunity Decision Engine (spec section 6).

Deterministic, measurable scoring -- not an LLM opinion. Weights are
configurable via the `scoring_weights` OperatingPolicy row (defaults set in
app/bootstrap.py, matching spec section 5's example weights). Missing or
unavailable evidence REDUCES confidence and score; it is never treated as
proof of demand.
"""
from __future__ import annotations

from app.agents.base import BaseAgent
from app.models.models import MarketOpportunity, OperatingPolicy, OpportunityScore

DEFAULT_WEIGHTS = {
    "demand_evidence": 0.25,
    # Lowered from 0.20 (2026-10-14, owner directive): raw listing-count
    # saturation matters less than proof of what's actually resonating --
    # "I don't care if 9 million chore charts are being listed if they
    # don't sell." Kept as a real signal, just no longer weighted as if
    # it were the primary one.
    "competitive_opportunity": 0.10,
    "estimated_profitability": 0.25,
    "production_feasibility": 0.15,
    # Raised from 0.10 (2026-10-14): this is now a real "proven winner"
    # signal (see score_opportunity()'s differentiation_score), not a flat
    # 0.50 placeholder -- it's the direct operationalization of "chase
    # what design and product is selling the most and piggy back off of
    # that," so it carries real weight now.
    "differentiation_potential": 0.20,
    "risk": 0.05,
}

MINIMUM_SCORE_DEFAULT = 0.55

# Real market-saturation thresholds -- active Etsy listing count for the
# keyword (app/agents/market_intelligence.py now fetches this for real via
# app/integrations/etsy.py:get_active_listing_count) mapped to a competitive-
# opportunity score. Lower listing count = less saturated = better
# opportunity for a new entrant. The specific cutoffs are a judgment call
# (there's no single "correct" saturation curve), but they're applied to a
# real retrieved number, not a guess -- confirmed live: "cross necklace"
# (218k listings, highly saturated) vs "printable chore chart" (36k,
# moderate) vs a long-tail niche keyword (under 1k, wide open) are real,
# meaningfully different numbers this curve should treat differently.
_COMPETITION_THRESHOLDS = [
    (500, 0.90),
    (2_000, 0.75),
    (10_000, 0.55),
    (50_000, 0.35),
    (200_000, 0.20),
]
_COMPETITION_SATURATED_SCORE = 0.10


def _competition_score_from_listing_count(count: int) -> float:
    for ceiling, score in _COMPETITION_THRESHOLDS:
        if count < ceiling:
            return score
    return _COMPETITION_SATURATED_SCORE


class OpportunityDecisionEngine(BaseAgent):
    key = "opportunity_engine"

    def _get_weights(self) -> dict:
        row = self.db.query(OperatingPolicy).filter(OperatingPolicy.key == "scoring_weights").first()
        return row.value if row else DEFAULT_WEIGHTS

    def _get_minimum_score(self) -> float:
        row = self.db.query(OperatingPolicy).filter(OperatingPolicy.key == "minimum_opportunity_score").first()
        if row is not None and isinstance(row.value, (int, float)):
            return float(row.value)
        return MINIMUM_SCORE_DEFAULT

    def score_opportunity(self, opportunity: MarketOpportunity) -> OpportunityScore:
        evidence = opportunity.evidence_summary or {}
        weights = self._get_weights()

        # --- Demand evidence: driven by real Google Trends average interest.
        if evidence.get("is_real_data") and evidence.get("average_interest_0_100") is not None:
            demand_score = min(1.0, evidence["average_interest_0_100"] / 60.0)
            if evidence.get("trend_direction") == "rising":
                demand_score = min(1.0, demand_score + 0.1)
            confidence = "medium"
        else:
            # No verifiable evidence -> score is penalized, not guessed upward.
            demand_score = 0.15
            confidence = "low"

        # --- Competitive opportunity: real Etsy active-listing count when available
        # (market_intelligence.py fetches this live), never a guess otherwise --
        # same "missing evidence reduces confidence" rule as demand above.
        if evidence.get("etsy_competition_is_real") and evidence.get("etsy_listing_count") is not None:
            competition_score = _competition_score_from_listing_count(evidence["etsy_listing_count"])
        else:
            competition_score = 0.40  # neutral/unknown, deliberately not optimistic
            confidence = "low"

        # --- Profitability / feasibility / differentiation / risk: category-based heuristics
        # (digital products: low production cost & complexity; POD: moderate cost/complexity).
        if opportunity.category == "digital":
            profitability_score = 0.75
            feasibility_score = 0.85
            risk_score = 0.80  # higher = lower risk
        else:  # pod
            profitability_score = 0.55
            feasibility_score = 0.60
            risk_score = 0.65

        # --- Differentiation: real "what's actually winning" signal (owner directive,
        # 2026-10-14: "we need to be looking at what is selling... chase what design
        # and product is selling the most and piggy back off of that" -- NOT raw
        # listing-count saturation, which was the wrong lever and got explicitly
        # rejected). market_intelligence.py's _get_market_signal() fetches the real
        # top-favorited Etsy listings for this keyword; a real standout (one listing
        # pulling disproportionate favorites vs. the sample median) is evidence a
        # specific approach is proven to resonate, which is what should be chased --
        # the opposite of how this same ratio would read as a saturation risk.
        market_signal = evidence.get("market_signal")
        if evidence.get("market_signal_is_real") and market_signal:
            differentiation_score = market_signal["standout_score"]
        else:
            differentiation_score = 0.40  # neutral/unknown, deliberately not optimistic
            confidence = "low"

        weighted_total = (
            demand_score * weights.get("demand_evidence", DEFAULT_WEIGHTS["demand_evidence"])
            + competition_score * weights.get("competitive_opportunity", DEFAULT_WEIGHTS["competitive_opportunity"])
            + profitability_score * weights.get("estimated_profitability", DEFAULT_WEIGHTS["estimated_profitability"])
            + feasibility_score * weights.get("production_feasibility", DEFAULT_WEIGHTS["production_feasibility"])
            + differentiation_score * weights.get("differentiation_potential", DEFAULT_WEIGHTS["differentiation_potential"])
            + risk_score * weights.get("risk", DEFAULT_WEIGHTS["risk"])
        )

        minimum = self._get_minimum_score()
        decision = "selected" if weighted_total >= minimum else "rejected"
        if confidence == "low" and weighted_total < minimum + 0.1:
            decision = "needs_more_research" if decision == "selected" else decision

        if evidence.get("market_signal_is_real") and market_signal:
            signal_note = (
                f"real standout found (top real listing '{market_signal['top_listing_title'][:60]}' has "
                f"{market_signal['top_listing_favorites']} favorites vs. a {market_signal['median_favorites']:.0f} "
                f"median across the top {market_signal['sample_size']}, ratio {market_signal['standout_ratio']}x)"
            )
        else:
            signal_note = "no real market-signal data available this run"

        rationale = (
            f"Weighted score {weighted_total:.2f} vs minimum {minimum:.2f}. "
            f"Demand evidence {'REAL (Google Trends)' if evidence.get('is_real_data') else 'UNAVAILABLE'}"
            f"(score {demand_score:.2f}). Competitive data (score {competition_score:.2f}): "
            f"{evidence.get('etsy_competition_data', 'n/a')}. "
            f"Differentiation/proven-winner signal (score {differentiation_score:.2f}): {signal_note}. "
            f"Category defaults applied for profitability/feasibility/risk ({opportunity.category})."
        )

        score = OpportunityScore(
            opportunity_id=opportunity.id,
            demand_score=round(demand_score, 3),
            competition_score=round(competition_score, 3),
            profitability_score=round(profitability_score, 3),
            feasibility_score=round(feasibility_score, 3),
            differentiation_score=round(differentiation_score, 3),
            risk_score=round(risk_score, 3),
            weights=weights,
            weighted_total=round(weighted_total, 3),
            confidence_level=confidence,
            rationale=rationale,
            decision=decision,
        )
        self.db.add(score)
        self.db.commit()
        self.db.refresh(score)

        self.log(
            "opportunity_scored",
            f"{opportunity.niche_title}: {weighted_total:.2f} -> {decision}",
            {"opportunity_id": opportunity.id, "score_id": score.id, "decision": decision},
        )
        return score

    def select_best(self, opportunities: list[MarketOpportunity]) -> MarketOpportunity | None:
        """Scores all candidates; returns the best 'selected' one, or None if all were rejected."""
        scored: list[tuple[MarketOpportunity, OpportunityScore]] = []
        for opp in opportunities:
            score = self.score_opportunity(opp)
            scored.append((opp, score))

        selected = [(o, s) for o, s in scored if s.decision == "selected"]
        if not selected:
            self.log("no_opportunity_selected", "All researched opportunities fell below the minimum score/confidence bar.")
            return None

        best_opp, best_score = max(selected, key=lambda pair: pair[1].weighted_total)
        return best_opp
