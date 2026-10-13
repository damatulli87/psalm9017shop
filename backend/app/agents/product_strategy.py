"""Product Strategy Agent (spec section 7): opportunity -> structured spec."""
from __future__ import annotations

import json
import re

from app.agents.base import BaseAgent
from app.integrations import ai_providers
from app.models.models import MarketOpportunity, ProductSpecification

DIGITAL_FORMAT_BY_NICHE = {
    "Printable Budget Planners": ("xlsx", 9.00),
    "Wedding Planning Templates": ("pdf", 14.00),
    "Printable Chore Charts": ("pdf", 5.00),
    "Small Business Invoice Templates": ("xlsx", 7.00),
    "Printable Daily Planners": ("pdf", 8.00),
    "Digital Journal Templates": ("pdf", 10.00),
    "Home Office Productivity Planners": ("xlsx", 9.00),
    "Bible Verse Printable Wall Art": ("pdf", 6.00),
    "Prayer Journal Printable": ("pdf", 8.00),
    "Bible Study Planner": ("pdf", 9.00),
    "Sunday School Activity Worksheets": ("pdf", 5.00),
    "Weekly Meal Planner Printable": ("pdf", 7.00),
    "Habit Tracker Printable": ("pdf", 5.00),
    "Workout Planner Printable": ("pdf", 7.00),
    "Baby Shower Planning Printable": ("pdf", 6.00),
    "Wedding Seating Chart Template": ("pdf", 12.00),
    "Social Media Content Planner Printable": ("pdf", 8.00),
    "Debt Payoff Tracker Printable": ("pdf", 6.00),
}
# Prices set with a real margin above verified Printify fulfillment cost
# (see app/agents/pod_production.py catalog comments for the real cost each
# product type returned) -- not arbitrary guesses.
# Prices assume FREE shipping to the buyer (shipping cost absorbed here,
# not charged separately -- see ETSY_SHIPPING_PROFILE_ID in backend/.env).
# Set 2026-10-13 from real Printify cost + real worst-case US shipping
# quote (via /catalog/.../shipping.json) plus a real competitive-pricing
# check (Etsy listing-price research for each category), not guessed:
#   type      real cost  real ship(worst)  price   margin(worst case)
#   tshirt    $11.77     $7.99             $26.00  $6.24   (market ~$20-28)
#   mug       $6.44      $7.29             $19.00  $5.27   (market ~$16-25)
#   hoodie    $40.84     $8.79             $56.00  $6.37   (market ~$35-50 -- priced above the
#                                                            typical range deliberately: owner
#                                                            confirmed comfort/quality matters more
#                                                            than lowest cost, so this stays on
#                                                            Bella+Canvas [most-cited "soft, quality
#                                                            blank" pick] rather than a cheaper
#                                                            Gildan option, and the price reflects
#                                                            that real cost rather than chasing the
#                                                            market median)
#   tote      $20.05     $6.09             $32.00  $5.86   (market ~$18-20 median, up to $35)
#   sticker   $2.32      $4.59             $8.00   $1.09   (market singles ~$3.50-5; thin margin
#                                                            is normal for single stickers)
#   cap       $15.38     $5.09             $27.00  $6.53   (market ~$25-27)
#   necklace  $13.47     $5.89             $34.00  $14.64  (market ~$30-46 for cross/pendant)
#   notebook  $15.63     $6.19             $28.00  $6.18   (market ~$24-30)
#   tumbler   $24.97     $6.69             $38.00  $6.34   (market ~$25 median, $25-50 common)
POD_FORMAT_BY_NICHE = {
    "Funny Cat-Lover T-Shirts": ("tshirt", 26.00),
    "Motivational Quote Mugs": ("mug", 19.00),
    "Teacher Appreciation POD Gifts": ("tshirt", 26.00),
    "Faith-Based Graphic T-Shirts": ("tshirt", 26.00),
    "Scripture Verse Coffee Mugs": ("mug", 19.00),
    "Christian Faith Pullover Hoodies": ("hoodie", 56.00),
    "Dog Mom Pullover Hoodies": ("hoodie", 56.00),
    "Wedding Party Tote Bags": ("tote", 32.00),
    "Teacher Appreciation Tote Bags": ("tote", 32.00),
    "Motivational Quote Sticker Packs": ("sticker", 8.00),
    "Christian Faith Sticker Packs": ("sticker", 8.00),
    "Nurse Appreciation T-Shirts": ("tshirt", 26.00),
    "Zodiac Sign Coffee Mugs": ("mug", 19.00),
    "Christian Faith Baseball Caps": ("cap", 27.00),
    "Faith Cross Necklaces": ("necklace", 34.00),
    "Daily Gratitude Journal Notebooks": ("notebook", 28.00),
    "Motivational Quote Tumblers": ("tumbler", 38.00),
}

_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def _parse_narrative(raw_text: str) -> tuple[str, str] | None:
    """Try to pull {target_customer, problem_solved} out of a real AI
    response. Models sometimes wrap JSON in markdown fences despite being
    asked not to -- strip those before parsing. Returns None (caller keeps
    the generic fallback) rather than raising on anything malformed."""
    cleaned = _JSON_FENCE_RE.sub("", raw_text.strip())
    try:
        parsed = json.loads(cleaned)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(parsed, dict):
        return None
    target_customer = parsed.get("target_customer")
    problem_solved = parsed.get("problem_solved")
    if isinstance(target_customer, str) and isinstance(problem_solved, str) and target_customer and problem_solved:
        return target_customer.strip(), problem_solved.strip()
    return None


class ProductStrategyAgent(BaseAgent):
    key = "product_strategy"

    def build_spec(self, opportunity: MarketOpportunity, workflow_run_id: int | None = None) -> ProductSpecification:
        if opportunity.category == "digital":
            fmt, price = DIGITAL_FORMAT_BY_NICHE.get(opportunity.niche_title, ("pdf", 9.00))
            est_cost = 0.50  # negligible marginal cost: AI time + storage
        else:
            fmt, price = POD_FORMAT_BY_NICHE.get(opportunity.niche_title, ("tshirt", 22.00))
            est_cost = 11.00  # placeholder blank-garment + print cost, to be replaced by real Printify/Printful quote

        margin = round(price - est_cost, 2)

        ai_resp = ai_providers.complete(
            self.db,
            agent_key=self.key,
            system_prompt=self.record.system_prompt,
            user_prompt=(
                f"For a {opportunity.category} product in the niche '{opportunity.niche_title}', write:\n"
                f"1. A specific target customer description -- who exactly buys this (1-2 sentences, concrete, "
                f"not generic).\n"
                f"2. A specific problem/benefit statement -- what real problem this solves for them (1 sentence). "
                f"Avoid vague filler like 'addresses needs within the niche.'\n\n"
                f"Evidence: {json.dumps(opportunity.evidence_summary)}\n\n"
                f'Respond with ONLY valid JSON, no markdown fences: '
                f'{{"target_customer": "...", "problem_solved": "..."}}'
            ),
            task_hint="product_spec_narrative",
            complexity="routine",
            workflow_run_id=workflow_run_id,
        )

        # Generic fallback used whenever there's no real AI call, or a real
        # call returned something that didn't parse as the requested JSON --
        # a malformed model response must never break product creation.
        target_customer_text = ai_resp.text
        problem_solved_text = f"Helps the target customer address needs within the '{opportunity.niche_title}' niche."
        narrative_is_ai = False

        if not ai_resp.is_mock:
            parsed = _parse_narrative(ai_resp.text)
            if parsed:
                target_customer_text, problem_solved_text = parsed
                narrative_is_ai = True
            else:
                self.log(
                    "product_spec_ai_parse_failed",
                    f"AI response for opportunity #{opportunity.id} wasn't valid JSON -- using generic problem_solved fallback.",
                    {"raw_response": ai_resp.text[:500]},
                )

        spec = ProductSpecification(
            opportunity_id=opportunity.id,
            title=f"{opportunity.niche_title} - Starter Edition",
            product_type=opportunity.category,
            target_customer=target_customer_text,
            target_customer_is_ai=narrative_is_ai,
            problem_solved=problem_solved_text,
            format=fmt,
            design_brief={},
            recommended_price_usd=price,
            estimated_cost_usd=est_cost,
            estimated_margin_usd=margin,
            status="planned",
        )
        self.db.add(spec)
        self.db.commit()
        self.db.refresh(spec)

        self.log(
            "product_spec_created",
            f"Spec #{spec.id} for '{spec.title}' ({fmt}, ${price:.2f}, margin ${margin:.2f})",
            {"product_id": spec.id, "ai_provider": ai_resp.provider, "ai_is_mock": ai_resp.is_mock,
             "narrative_is_ai": narrative_is_ai},
        )
        return spec
