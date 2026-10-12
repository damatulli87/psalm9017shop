"""Product Strategy Agent (spec section 7): opportunity -> structured spec."""
from __future__ import annotations

import json

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
                f"Draft a one-paragraph target-customer and problem statement for a {opportunity.category} "
                f"product in the niche '{opportunity.niche_title}'. Evidence: {json.dumps(opportunity.evidence_summary)}"
            ),
            task_hint="product_spec_narrative",
            complexity="routine",
            workflow_run_id=workflow_run_id,
        )

        spec = ProductSpecification(
            opportunity_id=opportunity.id,
            title=f"{opportunity.niche_title} - Starter Edition",
            product_type=opportunity.category,
            target_customer=ai_resp.text,
            target_customer_is_ai=not ai_resp.is_mock,
            problem_solved=f"Helps the target customer address needs within the '{opportunity.niche_title}' niche.",
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
            {"product_id": spec.id, "ai_provider": ai_resp.provider, "ai_is_mock": ai_resp.is_mock},
        )
        return spec
