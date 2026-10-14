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
    "competitive_opportunity": 0.20,
    "estimated_profitability": 0.25,
    "production_feasibility": 0.15,
    "differentiation_potential": 0.10,
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

        # Real competitive search exists now (app/integrations/etsy.py:search_top_listings,
        # used for design-style research), but isn't wired into this specific dimension yet --
        # e.g. favorites-concentration across top results as a differentiation proxy. Left as
        # a neutral placeholder rather than building an under-verified scoring heuristic.
        differentiation_score = 0.50

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

        rationale = (
            f"Weighted score {weighted_total:.2f} vs minimum {minimum:.2f}. "
            f"Demand evidence {'REAL (Google Trends)' if evidence.get('is_real_data') else 'UNAVAILABLE'}"
            f"(score {demand_score:.2f}). Competitive data (score {competition_score:.2f}): "
            f"{evidence.get('etsy_competition_data', 'n/a')}. "
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
