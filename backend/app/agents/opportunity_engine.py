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

        # --- Competitive opportunity: Etsy data unavailable without credentials -> capped low-confidence midpoint.
        competition_score = 0.40  # neutral/unknown, deliberately not optimistic
        if "BLOCKED" in str(evidence.get("etsy_competition_data", "")):
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

        differentiation_score = 0.50  # unknown without real competitive data; neutral default

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
            f"(score {demand_score:.2f}). Competitive data: {evidence.get('etsy_competition_data', 'n/a')}. "
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
