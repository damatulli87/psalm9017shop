"""Etsy Store Management Agent (spec section 12)."""
from __future__ import annotations

from app.agents.base import BaseAgent
from app.config import settings
from app.integrations import oauth_store
from app.integrations.etsy import create_draft_listing
from app.models.models import MarketplaceListing, ProductSpecification


class EtsyManagerAgent(BaseAgent):
    key = "etsy_manager"

    def prepare_listing_draft(self, product: ProductSpecification, *, seo_title: str, seo_description: str,
                               tags: list[str]) -> MarketplaceListing:
        access_token = oauth_store.get_valid_etsy_token(self.db)
        result = create_draft_listing(
            access_token=access_token,
            title=seo_title,
            description=seo_description,
            price_usd=product.recommended_price_usd,
            tags=tags,
            is_digital=(product.product_type == "digital"),
        )

        listing = MarketplaceListing(
            product_id=product.id,
            storefront_channel="etsy",
            external_listing_id=result.external_listing_id,
            title=seo_title,
            description=seo_description,
            price_usd=product.recommended_price_usd,
            tags=tags,
            is_simulated=result.simulated,
            status="draft",
        )
        self.db.add(listing)
        self.db.commit()
        self.db.refresh(listing)

        self.log(
            "listing_draft_prepared",
            f"Etsy draft for product #{product.id}: {'SIMULATED' if result.simulated else 'REAL'} -- {result.detail}",
            {"listing_id": listing.id, "etsy_configured": settings.etsy_configured},
        )
        return listing
