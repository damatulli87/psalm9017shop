"""Creative Director Agent (spec section 8): design brief + brand consistency."""
from __future__ import annotations

from app.agents.base import BaseAgent
from app.models.models import ProductSpecification

PALETTES = {
    "digital": {"primary": "#1B4332", "secondary": "#40916C", "accent": "#D8F3DC", "text": "#081C15"},
    "pod": {"primary": "#212529", "secondary": "#495057", "accent": "#FFD43B", "text": "#F8F9FA"},
}


class CreativeDirectorAgent(BaseAgent):
    key = "creative_director"

    def create_design_brief(self, product: ProductSpecification) -> dict:
        palette = PALETTES.get(product.product_type, PALETTES["digital"])
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
