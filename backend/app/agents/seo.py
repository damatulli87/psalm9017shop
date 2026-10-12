"""SEO Agent (spec section 14): titles, descriptions, tags from real product data (no stuffing/fake urgency)."""
from __future__ import annotations

from app.agents.base import BaseAgent
from app.models.models import MarketOpportunity, ProductSpecification

BANNED_PHRASES = ["limited time", "only today", "act now", "guaranteed results"]


class SEOAgent(BaseAgent):
    key = "seo"

    def build_listing_copy(self, product: ProductSpecification, opportunity: MarketOpportunity | None) -> dict:
        niche = opportunity.niche_title if opportunity else product.title
        title = f"{product.title} | Printable {niche} | Instant Digital Download" \
            if product.product_type == "digital" else f"{product.title} | {niche}"
        title = title[:140]

        description = (
            f"{product.title}\n\n"
            f"{product.problem_solved}\n\n"
            f"Format: {product.format.upper()}. "
            f"{'Instant digital download -- no physical item is shipped.' if product.product_type == 'digital' else 'Printed and shipped by our production partner.'}\n\n"
            "This listing was created with the assistance of AI-based design and writing tools, reviewed "
            "before publication. Production partner and AI-assistance disclosures are included per marketplace policy."
        )

        for phrase in BANNED_PHRASES:
            if phrase in description.lower():
                raise ValueError(f"Blocked deceptive phrase in generated copy: '{phrase}'")

        base_tags = niche.lower().replace("-", " ").split()
        tags = list(dict.fromkeys(base_tags + [product.format, product.product_type, "ultron commerce"]))[:13]

        copy = {"title": title, "description": description, "tags": tags}
        self.log("listing_copy_generated", f"SEO copy prepared for product #{product.id}", copy)
        return copy
