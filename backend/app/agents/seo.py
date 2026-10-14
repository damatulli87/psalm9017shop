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

import json
import re

from app.agents.base import BaseAgent
from app.integrations import ai_providers
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


_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def _fallback_tags(niche: str, product: ProductSpecification) -> list[str]:
    """Used when no real AI key is configured -- real buyer-relevant words
    only (niche keywords + format), never internal/dev terms like a brand
    or build-system name that has nothing to do with what a buyer searches
    for (confirmed live: an "ultron commerce" tag ended up on a real
    listing this way)."""
    base = niche.lower().replace("-", " ").split()
    extra = [product.format] if product.product_type != "digital" else ["printable", "digital download"]
    return list(dict.fromkeys(base + extra))[:13]


def _truncate_tag(raw: str, max_len: int = 20) -> str | None:
    """Real bug found live (2026-10-14): the AI is told tags must be <=20
    chars but doesn't reliably respect that, and a plain `tag[:20]` slice
    cut tags mid-word -- real examples that reached a real listing:
    "chore chart printabl" (should be "printable"), "kids responsibility "
    (trailing space, word cut clean off). Truncates at the last real word
    boundary within the limit instead; if even the first word alone
    exceeds the limit, drops the tag entirely rather than mutilating it."""
    tag = raw.strip()
    if not tag:
        return None
    if len(tag) <= max_len:
        return tag
    truncated = tag[:max_len]
    last_space = truncated.rfind(" ")
    return truncated[:last_space].strip() if last_space > 0 else None


def _ai_tags(db, agent_key: str, product: ProductSpecification, niche: str) -> list[str] | None:
    """Real Etsy tags should be phrases a buyer would actually search --
    not a mechanical split of the niche name. Asks the real model for
    buyer-search-style tags; returns None (caller falls back) on a mock
    response or anything that doesn't parse as the requested JSON array."""
    resp = ai_providers.complete(
        db,
        agent_key=agent_key,
        system_prompt="You write Etsy listing tags. Respond with ONLY a JSON array of strings, nothing else.",
        user_prompt=(
            f"Niche: {niche}\nProduct type: {product.format}\nTarget buyer: {product.target_customer}\n\n"
            f"Give up to 13 Etsy tags (each max 20 characters, multi-word phrases allowed) that a real buyer "
            f"would actually type into Etsy search to find this item. Favor specific, descriptive buyer-search "
            f"phrases over generic single words. Do not include the seller's shop/brand name or any internal "
            f"tool/platform name. Respond with ONLY a JSON array of strings."
        ),
        task_hint="listing_tags",
        complexity="routine",
    )
    if resp.is_mock:
        return None
    try:
        parsed = json.loads(_JSON_FENCE_RE.sub("", resp.text.strip()))
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(parsed, list) or not all(isinstance(t, str) for t in parsed):
        return None
    tags = [t for t in (_truncate_tag(raw) for raw in parsed) if t]
    return list(dict.fromkeys(tags))[:13] or None


class SEOAgent(BaseAgent):
    key = "seo"

    def build_listing_copy(self, product: ProductSpecification, opportunity: MarketOpportunity | None) -> dict:
        niche = opportunity.niche_title if opportunity else product.title
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

        tags = _ai_tags(self.db, self.key, product, niche) or _fallback_tags(niche, product)

        for phrase in BANNED_PHRASES:
            if phrase in description.lower() or any(phrase in t.lower() for t in tags):
                raise ValueError(f"Blocked deceptive phrase in generated copy: '{phrase}'")

        copy = {"title": title, "description": description, "tags": tags}
        self.log(
            "listing_copy_generated",
            f"SEO copy prepared for product #{product.id} (ai_disclosed={product.target_customer_is_ai})",
            copy,
        )
        return copy
