"""
SEO Agent (spec section 14): titles, descriptions, tags from real product
data (no stuffing/fake urgency).

AI disclosure (Etsy Creativity Standards: "Sellers must disclose within
their listing description if an item is created with the use of AI"): the
disclosure sentence is only ever added when `product.target_customer_is_ai`
is actually True -- i.e. a real AI provider (not the MOCK_LLM fallback)
actually generated content incorporated into this listing. Claiming AI
involvement that didn't happen is exactly the kind of inaccurate
representation the Seller Policy separately prohibits, so this must never
be a static boilerplate line. `AI_DISCLOSURE_MARKER` is checked verbatim by
`UltronSupervisorAgent.verify_ai_disclosure_accuracy` to independently
confirm the disclosure is present if and only if it should be.
"""
from __future__ import annotations

from app.agents.base import BaseAgent
from app.models.models import MarketOpportunity, ProductSpecification

BANNED_PHRASES = ["limited time", "only today", "act now", "guaranteed results"]
AI_DISCLOSURE_MARKER = "assistance of AI tools"

# Real material facts for the standard blank used per POD product type (see
# app/agents/pod_production.py for the actual Printify blueprint each one
# maps to) -- added after a real listing was confirmed to look sparse with
# just a one-line format note. Not marketing fluff, just what the item
# actually is.
POD_MATERIALS_BY_FORMAT = {
    "tshirt": "100% combed, ring-spun cotton (heather colors are cotton/poly blend)",
    "mug": "11oz ceramic, dishwasher and microwave safe",
    "hoodie": "Sponge fleece cotton/polyester blend, soft and warm",
    "tote": "Durable canvas",
    "sticker": "Weatherproof vinyl, kiss-cut",
    "cap": "Cotton twill, adjustable",
    "necklace": "Stainless steel pendant, one size",
    "notebook": "Hardcover, 5.5\" x 8.5\"",
    "tumbler": "Insulated 20oz stainless steel, double-wall",
}


def _clean_ai_narrative(raw: str) -> str | None:
    """target_customer holds the raw AI response text. Keep listing copy to a
    short, clean paragraph -- truncate rather than dump a long raw completion
    into the description."""
    text = raw.strip()
    if not text:
        return None
    return text[:400].rsplit(". ", 1)[0] + "." if len(text) > 400 else text


class SEOAgent(BaseAgent):
    key = "seo"

    def build_listing_copy(self, product: ProductSpecification, opportunity: MarketOpportunity | None) -> dict:
        niche = opportunity.niche_title if opportunity else product.title
        # product.title already includes the niche name ("<niche> - Starter
        # Edition"), so appending niche again here produced a visibly
        # duplicated title on a real listing ("X - Starter Edition | X") --
        # confirmed live. Add a real differentiator instead of repeating it.
        title = f"{product.title} - Printable Instant Download" \
            if product.product_type == "digital" else f"{product.title} - Custom {product.format.title()} Gift"
        title = title[:140]

        parts = [
            product.title,
            "",
            product.problem_solved,
            "",
        ]
        if product.product_type == "digital":
            parts.append(f"Format: {product.format.upper()}. Instant digital download -- no physical item is shipped.")
        else:
            material = POD_MATERIALS_BY_FORMAT.get(product.format)
            details = [f"Material: {material}." if material else None, "Made to order and shipped by our production partner.", "Free shipping. Processing time: 10 business days before shipment."]
            parts.append("\n".join(d for d in details if d))

        if product.target_customer_is_ai:
            narrative = _clean_ai_narrative(product.target_customer)
            if narrative:
                parts += ["", narrative]
            parts += ["", f"Parts of this listing's description were generated with the {AI_DISCLOSURE_MARKER}, "
                           "guided and reviewed by the seller before publication."]

        description = "\n".join(parts)

        for phrase in BANNED_PHRASES:
            if phrase in description.lower():
                raise ValueError(f"Blocked deceptive phrase in generated copy: '{phrase}'")

        base_tags = niche.lower().replace("-", " ").split()
        tags = list(dict.fromkeys(base_tags + [product.format, product.product_type, "ultron commerce"]))[:13]

        copy = {"title": title, "description": description, "tags": tags}
        self.log(
            "listing_copy_generated",
            f"SEO copy prepared for product #{product.id} (ai_disclosed={product.target_customer_is_ai})",
            copy,
        )
        return copy
