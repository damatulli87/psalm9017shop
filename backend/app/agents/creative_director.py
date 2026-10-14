"""Creative Director Agent (spec section 8): design brief + brand consistency."""
from __future__ import annotations

from app.agents.base import BaseAgent
from app.models.models import ProductSpecification

# Real themed palettes for digital products -- replaces the single flat
# dark-green palette every digital niche used to get regardless of what it
# actually was (a kids' chore chart and a wedding budget tracker looked
# identical). Picked by real keyword match against the niche title, not
# randomly, so a niche's look is at least directionally appropriate to its
# real audience. "pod" below is unrelated and unchanged -- it drives
# garment/POD *artwork* color, a separate concern from page layout color.
DIGITAL_PALETTE_THEMES: dict[str, dict] = {
    "playful": {  # kids, chores, routines, rewards
        "primary": "#2EC4B6", "secondary": "#F26B6B", "accent": "#FFF8EC",
        "highlight": "#FFC83D", "text": "#1B4332",
    },
    "elegant": {  # wedding, events
        "primary": "#A9746E", "secondary": "#D4A5A5", "accent": "#FAF3F0",
        "highlight": "#C9A227", "text": "#4A3B3B",
    },
    "professional": {  # budgets, invoices, business, debt payoff
        "primary": "#1D3557", "secondary": "#457B9D", "accent": "#F1FAEE",
        "highlight": "#E9C46A", "text": "#1D3557",
    },
    "faith": {  # bible, prayer, scripture, sunday school
        "primary": "#4A5D23", "secondary": "#C9A227", "accent": "#FBF7EE",
        "highlight": "#8B5E34", "text": "#3E2C1C",
    },
    "default": {  # anything unmatched -- the original brand-adjacent look
        "primary": "#1B4332", "secondary": "#40916C", "accent": "#D8F3DC",
        "highlight": "#95D5B2", "text": "#081C15",
    },
}
_THEME_KEYWORDS: dict[str, tuple[str, ...]] = {
    "playful": ("chore", "kid", "toddler", "routine", "reward", "sticker", "allowance", "habit"),
    "elegant": ("wedding",),
    "professional": ("budget", "finance", "invoice", "business", "debt", "bookkeeping"),
    "faith": ("bible", "prayer", "scripture", "sunday school", "faith"),
}

PALETTES = {
    "digital": DIGITAL_PALETTE_THEMES["default"],
    "pod": {"primary": "#212529", "secondary": "#495057", "accent": "#FFD43B", "text": "#F8F9FA"},
}


def _digital_palette_for(title: str) -> dict:
    lowered = title.lower()
    for theme, keywords in _THEME_KEYWORDS.items():
        if any(kw in lowered for kw in keywords):
            return DIGITAL_PALETTE_THEMES[theme]
    return DIGITAL_PALETTE_THEMES["default"]


class CreativeDirectorAgent(BaseAgent):
    key = "creative_director"

    def create_design_brief(self, product: ProductSpecification) -> dict:
        palette = _digital_palette_for(product.title) if product.product_type == "digital" else PALETTES["pod"]
        brief = {
            "layout": "single-column cover + grid-based interior pages" if product.product_type == "digital"
                      else "centered print area, 300dpi, transparent background",
            "typography": {"heading": "Helvetica-Bold", "body": "Helvetica"},
            "palette": palette,
            "originality_statement": (
                "Design is generated from scratch using the palette/typography above. No third-party "
                "artwork, logos, characters, or trademarks are referenced. Any uncertain IP question is "
                "flagged for human review rather than resolved automatically."
            ),
            "ip_review_required": False,
        }
        product.design_brief = brief
        self.db.commit()
        self.log("design_brief_created", f"Design brief set for product #{product.id}", brief)
        return brief
