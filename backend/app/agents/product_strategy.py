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
}
POD_FORMAT_BY_NICHE = {
    "Funny Cat-Lover T-Shirts": ("tshirt", 24.00),
    "Motivational Quote Mugs": ("mug", 16.00),
    "Teacher Appreciation POD Gifts": ("tshirt", 22.00),
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
