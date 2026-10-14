"""Etsy Store Management Agent (spec section 12)."""
from __future__ import annotations

from pathlib import Path

import httpx

from app.agents.base import BaseAgent
from app.config import settings
from app.integrations import oauth_store
from app.integrations.etsy import create_draft_listing, upload_listing_file, upload_listing_image
from app.models.models import MarketplaceListing, ProductAsset, ProductSpecification

# Real Etsy seller-taxonomy leaf node ids (looked up live via
# GET /v3/application/seller-taxonomy/nodes on 2026-10-13, not guessed --
# a real listing creation call failed with "IDs must be >= 1, got 0" the
# first time it ran for real, since taxonomy_id was hardcoded to 0).
DIGITAL_TAXONOMY_BY_NICHE = {
    "Printable Chore Charts": 12479,  # Chore Chart Templates
    "Printable Budget Planners": 12487,  # Personal Finance Templates
    "Wedding Planning Templates": 12481,  # Event Program Templates
    "Small Business Invoice Templates": 12478,  # Bookkeeping Templates
    "Printable Daily Planners": 12476,  # Planner Templates
    "Digital Journal Templates": 12475,  # Journal Templates
    "Home Office Productivity Planners": 12476,  # Planner Templates
    "Bible Verse Printable Wall Art": 2078,  # Digital Prints
    "Prayer Journal Printable": 12475,  # Journal Templates
    "Bible Study Planner": 12476,  # Planner Templates
    "Sunday School Activity Worksheets": 12471,  # Worksheets
    "Weekly Meal Planner Printable": 12476,  # Planner Templates
    "Habit Tracker Printable": 12476,  # Planner Templates
    "Workout Planner Printable": 12476,  # Planner Templates
    "Baby Shower Planning Printable": 12481,  # Event Program Templates
    "Wedding Seating Chart Template": 12481,  # Event Program Templates
    "Social Media Content Planner Printable": 12486,  # Social Media Templates
    "Debt Payoff Tracker Printable": 12487,  # Personal Finance Templates
}
# POD taxonomy maps by physical product type (product.format), not niche --
# the category is about the physical item, not its theme.
POD_TAXONOMY_BY_FORMAT = {
    "tshirt": 482,  # Clothing > Gender-Neutral Adult Clothing > Tops & Tees > T-shirts
    "mug": 1062,  # Mugs
    "hoodie": 1853,  # Clothing > Gender-Neutral Adult Clothing > Hoodies & Sweatshirts > Hoodies
    "tote": 190,  # Bags & Purses > Totes
    "sticker": 1326,  # Stickers
    "cap": 25,  # Accessories > Hats & Head Coverings > Hats & Caps
    "necklace": 1229,  # Jewelry > Necklaces > Pendant Necklaces
    "notebook": 326,  # Journals & Notebooks
    "tumbler": 6729,  # Tumblers
}
# Safe, valid (non-zero) fallbacks for any niche added without a mapping
# above -- should never actually trigger since every current niche is
# mapped, but 0 is never valid, so this is the defensive floor.
_DIGITAL_TAXONOMY_FALLBACK = 2078  # Digital Prints
_POD_TAXONOMY_FALLBACK = 482  # T-shirts


def _taxonomy_id_for(product: ProductSpecification) -> int:
    if product.product_type == "digital":
        for niche_title, tax_id in DIGITAL_TAXONOMY_BY_NICHE.items():
            if product.title.startswith(niche_title):
                return tax_id
        return _DIGITAL_TAXONOMY_FALLBACK
    return POD_TAXONOMY_BY_FORMAT.get(product.format, _POD_TAXONOMY_FALLBACK)


def _listing_image_bytes(db, product: ProductSpecification) -> bytes | None:
    """For POD, Printify's own real mockup (the design shown on the actual
    physical product -- a proper product photo) is a far better listing
    image than the raw print artwork, so it's preferred when available.
    Falls back to our own generated/registered preview PNG otherwise."""
    if product.product_type != "digital":
        mockup_url = (product.design_brief or {}).get("pod", {}).get("mockup_image_url")
        if mockup_url:
            try:
                resp = httpx.get(mockup_url, timeout=15)
                resp.raise_for_status()
                return resp.content
            except Exception:  # noqa: BLE001
                pass  # fall through to the local asset below

    asset = db.query(ProductAsset).filter(
        ProductAsset.product_id == product.id, ProductAsset.asset_type == "png"
    ).first()
    if asset and Path(asset.file_path).exists():
        return Path(asset.file_path).read_bytes()
    return None


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
            taxonomy_id=_taxonomy_id_for(product),
        )

        # A real (non-simulated) API call can still fail -- confirmed live
        # (a bad taxonomy_id 400'd). That's NOT the same as a successful
        # simulated/real draft and must not be recorded as one, or the
        # pipeline would go on to request owner approval to publish a
        # listing that doesn't actually exist on Etsy.
        listing = MarketplaceListing(
            product_id=product.id,
            storefront_channel="etsy",
            external_listing_id=result.external_listing_id,
            title=seo_title,
            description=seo_description,
            price_usd=product.recommended_price_usd,
            tags=tags,
            is_simulated=not result.success,
            status="draft" if (result.success or result.simulated) else "creation_failed",
        )
        self.db.add(listing)
        self.db.commit()
        self.db.refresh(listing)

        self.log(
            "listing_draft_prepared",
            f"Etsy draft for product #{product.id}: "
            f"{'SIMULATED' if result.simulated else ('REAL' if result.success else 'FAILED')} -- {result.detail}",
            {"listing_id": listing.id, "etsy_configured": settings.etsy_configured, "success": result.success},
        )

        # create_draft_listing() alone leaves the real listing with
        # images: null -- confirmed live (the first real listing created
        # had no photos). Etsy requires a separate upload call per image.
        if result.success and result.external_listing_id and access_token:
            image_bytes = _listing_image_bytes(self.db, product)
            if image_bytes:
                uploaded, detail = upload_listing_image(
                    access_token=access_token,
                    listing_id=result.external_listing_id,
                    image_bytes=image_bytes,
                    alt_text=product.title[:500],
                )
                self.log(
                    "listing_image_uploaded" if uploaded else "listing_image_upload_failed",
                    f"Listing #{listing.id} image upload: {detail}",
                    {"listing_id": listing.id, "uploaded": uploaded},
                )
            else:
                self.log(
                    "listing_image_upload_skipped",
                    f"No image available to upload for product #{product.id}.",
                    {"listing_id": listing.id},
                )

            # Confirmed live (2026-10-14): create_draft_listing(is_digital=True)
            # alone does NOT make Etsy treat this as a real download listing --
            # it's created as listing_type "physical" regardless, and only
            # flips to "download" once a real file is attached here. Without
            # this, a "successful" digital listing would ship a buyer nothing.
            # A digital product with no file attached is not a valid listing,
            # so a failure here downgrades listing.status the same way a
            # failed listing creation does -- not left as a silently broken
            # "draft" that could reach owner approval.
            if product.product_type == "digital":
                zip_asset = self.db.query(ProductAsset).filter(
                    ProductAsset.product_id == product.id, ProductAsset.asset_type == "zip"
                ).first()
                if zip_asset and Path(zip_asset.file_path).exists():
                    file_path = Path(zip_asset.file_path)
                    uploaded, detail = upload_listing_file(
                        access_token=access_token,
                        listing_id=result.external_listing_id,
                        file_bytes=file_path.read_bytes(),
                        file_name=file_path.name,
                    )
                    self.log(
                        "listing_file_uploaded" if uploaded else "listing_file_upload_failed",
                        f"Listing #{listing.id} digital file upload: {detail}",
                        {"listing_id": listing.id, "uploaded": uploaded},
                    )
                    if not uploaded:
                        listing.status = "creation_failed"
                        self.db.commit()
                else:
                    self.log(
                        "listing_file_upload_skipped",
                        f"No delivery ZIP found on disk for product #{product.id} -- "
                        f"cannot create a valid digital listing without it.",
                        {"listing_id": listing.id},
                    )
                    listing.status = "creation_failed"
                    self.db.commit()
        return listing
