"""Etsy Store Management Agent (spec section 12)."""
from __future__ import annotations

import re
from pathlib import Path

import httpx

from app.agents.base import BaseAgent
from app.agents.pod_production import _lookup_catalog
from app.config import settings
from app.integrations import oauth_store, printify
from app.integrations.etsy import (
    create_draft_listing,
    set_listing_inventory,
    upload_listing_file,
    upload_listing_image,
)
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

# Real Etsy "Primary color" property (property_id 200) -- confirmed live
# (2026-10-14, get_taxonomy_properties()) to be the SAME global property
# with the SAME 19 value_ids across every POD taxonomy used here (t-shirt,
# mug, hoodie, tote, sticker, cap, necklace, notebook, tumbler), not
# redefined per category. Keys are lowercased Etsy display names.
_ETSY_COLOR_VALUE_IDS: dict[str, int] = {
    "black": 1, "blue": 2, "brown": 3, "green": 4, "gray": 5, "orange": 6,
    "pink": 7, "purple": 8, "red": 9, "white": 10, "yellow": 11,
    "beige": 1213, "gold": 1214, "silver": 1215, "bronze": 1216,
    "rose gold": 1217, "copper": 1218, "clear": 1219, "rainbow": 1220,
}
# Printify blank colors that don't exactly match one of Etsy's 19 generic
# names -- mapped to the closest real bucket rather than dropping the
# color variation entirely. An approximation, not hidden as anything else.
_COLOR_ALIASES: dict[str, str] = {
    "khaki": "beige", "dark green": "green", "dark navy": "blue",
    "navy": "blue", "lime": "green", "turquoise": "blue",
}

# Real Etsy "Unisex shirt size" property (property_id 62809790533,
# scale_id 51 "Unisex letter size") -- confirmed live for both t-shirt
# (taxonomy 482) and hoodie (1853), the only two POD formats here that
# have a real discrete size *enum* Etsy recognizes. Other multi-size
# formats (tote, sticker) are physical dimensions, not a controlled
# vocabulary Etsy defines -- those use a free-text Custom1 property
# instead (see _build_inventory_products below).
_ETSY_SHIRT_SIZE_PROPERTY_ID = 62809790533
_ETSY_SHIRT_SIZE_SCALE_ID = 51
_ETSY_SHIRT_SIZE_VALUE_IDS: dict[str, int] = {
    "XXS": 2133, "XS": 2135, "S": 2137, "M": 2139, "L": 2141,
    "XL": 2144, "2X": 2147, "3X": 2149, "4X": 2151,
}
_ETSY_COLOR_PROPERTY_ID = 200
_ETSY_CUSTOM_SIZE_PROPERTY_ID = 513  # "Custom1" -- free-text, no controlled vocabulary
_ETSY_CUSTOM_COLOR_PROPERTY_ID = 514  # "Custom2" -- used only when the real bucketed-color fallback below would collide

# Per POD format: how (if at all) real Etsy listing variations should be
# built from Printify's real per-variant color/size options. "size": "enum"
# uses the real shirt-size property above; "custom" uses the free-text
# Custom1 property for a real physical dimension Etsy has no enum for;
# None means that axis doesn't vary for this format (e.g. cap/notebook are
# one size; mug/necklace/tumbler are a single real variant with nothing to
# choose, so no inventory call is made at all -- see _build_inventory_products).
POD_VARIATION_CONFIG: dict[str, dict] = {
    "tshirt": {"color": True, "size": "enum"},
    "hoodie": {"color": True, "size": "enum"},
    "tote": {"color": True, "size": "custom"},
    "sticker": {"color": False, "size": "custom"},
    "cap": {"color": True, "size": None},
    "notebook": {"color": True, "size": None},
}


def _normalize_shirt_size(raw: str) -> str | None:
    """Printify sizes this app actually uses are already S/M/L/XL, or
    "2XL" -- Etsy's real value names for the same sizes are S/M/L/XL, then
    "2X" (not "2XL"). Confirmed live against the real property's possible
    values; a plain string match would have silently matched nothing for
    any 2XL+ size."""
    raw = raw.strip().upper()
    if raw in _ETSY_SHIRT_SIZE_VALUE_IDS:
        return raw
    match = re.match(r"^(\d+)XL$", raw)
    if match:
        candidate = f"{match.group(1)}X"
        if candidate in _ETSY_SHIRT_SIZE_VALUE_IDS:
            return candidate
    return None


def _etsy_color_value_id(raw: str) -> tuple[str, int] | None:
    key = raw.strip().lower()
    key = _COLOR_ALIASES.get(key, key)
    value_id = _ETSY_COLOR_VALUE_IDS.get(key)
    if value_id is None:
        return None
    return key.title() if key != "white" else "White", value_id


def _colors_collide(real_color_names: set[str]) -> bool:
    """Real bug this caught before it ever reached a live listing: Printify's
    real notebook catalog has 8 distinct blank colors (Black/Blue/Lime/Navy/
    Orange/Red/Silver/Turquoise), but Etsy's 19-color generic bucket has no
    "Navy" or "Turquoise" -- both would silently collapse into the SAME
    "Blue" as the catalog's actual real Blue, making 3 of 8 variants
    indistinguishable to a buyer (and almost certainly rejected by Etsy as
    duplicate variations). Checked against the real distinct colors actually
    used by THIS product, not assumed safe just because the alias table
    resolves every name to *something*."""
    buckets = [_etsy_color_value_id(name) for name in real_color_names]
    resolved = [b[1] for b in buckets if b]
    return len(resolved) != len(set(resolved))


def _build_inventory_products(product: ProductSpecification, catalog: dict, price_usd: float) -> list[dict] | None:
    """Builds the real `products` array for set_listing_inventory() from
    Printify's own real per-variant option data -- never guessed. Returns
    None when there's nothing to vary (a single real variant has no real
    choice to offer a buyer, so no inventory call is made and the
    listing's default single price/quantity already correctly represents
    it)."""
    variant_ids = catalog.get("variant_ids") or []
    if len(variant_ids) <= 1:
        return None

    config = POD_VARIATION_CONFIG.get(product.format)
    if config is None:
        return None

    real_variants = {
        v["id"]: v.get("options", {})
        for v in printify.get_variants(catalog["blueprint_id"], catalog["print_provider_id"])
        if v["id"] in set(variant_ids)
    }

    # Decided once per product (not per variant): if Etsy's generic color
    # bucket would make two of THIS product's real distinct colors
    # indistinguishable, use the real literal color name as free text
    # instead of the lossy enum for every variant -- never a per-variant
    # mix of the two, which would make the listing's variations inconsistent.
    use_literal_color_names = False
    if config.get("color"):
        real_color_names = {
            (options.get("color") or options.get("surface"))
            for options in real_variants.values()
            if options.get("color") or options.get("surface")
        }
        use_literal_color_names = _colors_collide(real_color_names)

    products = []
    for variant_id in variant_ids:
        options = real_variants.get(variant_id, {})
        property_values = []

        if config.get("color"):
            color_raw = options.get("color") or options.get("surface")
            if color_raw and use_literal_color_names:
                property_values.append({
                    "property_id": _ETSY_CUSTOM_COLOR_PROPERTY_ID,
                    "property_name": "Color",
                    "value_ids": [],
                    "values": [color_raw],
                })
            elif color_raw:
                matched = _etsy_color_value_id(color_raw)
                if matched:
                    display_name, value_id = matched
                    property_values.append({
                        "property_id": _ETSY_COLOR_PROPERTY_ID,
                        "property_name": "Primary color",
                        "value_ids": [value_id],
                        "values": [display_name],
                    })

        size_mode = config.get("size")
        size_raw = options.get("size")
        if size_mode == "enum" and size_raw:
            normalized = _normalize_shirt_size(size_raw)
            if normalized:
                property_values.append({
                    "property_id": _ETSY_SHIRT_SIZE_PROPERTY_ID,
                    "property_name": "Size",
                    "scale_id": _ETSY_SHIRT_SIZE_SCALE_ID,
                    "value_ids": [_ETSY_SHIRT_SIZE_VALUE_IDS[normalized]],
                    "values": [normalized],
                })
        elif size_mode == "custom" and size_raw:
            property_values.append({
                "property_id": _ETSY_CUSTOM_SIZE_PROPERTY_ID,
                "property_name": "Size",
                "value_ids": [],
                "values": [size_raw],
            })

        if not property_values:
            continue  # nothing real to vary on for this axis -- skip rather than send an empty product

        products.append({
            "sku": str(variant_id),
            "property_values": property_values,
            # readiness_state_id here is required by the real inventory API
            # even though the listing itself already has one set at
            # creation -- confirmed live: omitting it 400s with "All
            # offerings need readiness state". Same shop-level id either way.
            "offerings": [{
                "price": round(price_usd, 2), "quantity": 999, "is_enabled": True,
                "readiness_state_id": settings.etsy_readiness_state_id,
            }],
        })

    return products or None


def _sku_on_property(inventory_products: list[dict]) -> list[int]:
    """Real top-level field the inventory PUT requires whenever products
    have distinct skus (confirmed live: omitting it 400s with "sku must be
    consistent across all products") -- the property_ids the sku actually
    varies by, read back from the products actually built rather than
    assumed from config (color may have switched to the literal-name
    Custom2 property at runtime if a collision was detected)."""
    return sorted({pv["property_id"] for p in inventory_products for pv in p["property_values"]})


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
            else:
                self._set_real_pod_variations(product, listing, access_token)
        return listing

    def _set_real_pod_variations(self, product: ProductSpecification, listing: MarketplaceListing,
                                  access_token: str) -> None:
        """Real fix for the known gap flagged in order_fulfillment.py: a POD
        listing with no real Etsy variations means a buyer can't actually
        pick a size/color, and fulfillment has no way to know which real
        Printify variant they wanted. Builds real property_values/offerings
        from Printify's own real per-variant option data (never guessed)
        and PUTs them via set_listing_inventory(). On success, stores the
        real {etsy_product_id: printify_variant_id} map Etsy hands back
        (sku was deliberately set to str(variant_id), so it's echoed
        unchanged) onto product.design_brief so order_fulfillment.py can
        look up exactly which variant a real buyer purchased instead of
        defaulting to the catalog's first listed one. Not fatal if it
        fails or doesn't apply (single-real-variant products like mug/
        necklace/tumbler correctly have nothing to vary) -- the listing is
        still a valid, sellable listing either way, just degraded to the
        pre-existing default-variant behavior, which is why this is logged
        as a concern rather than downgrading listing.status."""
        catalog = _lookup_catalog(product.title)
        if not catalog:
            return
        inventory_products = _build_inventory_products(product, catalog, product.recommended_price_usd)
        if not inventory_products:
            self.log(
                "listing_variations_not_applicable",
                f"Listing #{listing.id}: product #{product.id} has a single real Printify variant "
                f"or no configured variation mapping -- no real Etsy variations to set.",
                {"listing_id": listing.id},
            )
            return

        success, detail, real_products = set_listing_inventory(
            listing.external_listing_id, inventory_products,
            sku_on_property=_sku_on_property(inventory_products), access_token=access_token,
        )
        self.log(
            "listing_variations_set" if success else "listing_variations_failed",
            f"Listing #{listing.id} real Etsy variations: {detail}",
            {"listing_id": listing.id, "success": success, "variant_count": len(inventory_products)},
        )
        if not success:
            self._raise_concern(
                summary=f"Listing #{listing.id}: failed to set real Etsy size/color variations -- "
                        f"a buyer cannot pick a variant, and fulfillment will default to the catalog's "
                        f"first listed one for every order on this listing.",
                payload={"listing_id": listing.id, "product_id": product.id, "detail": detail},
            )
            return

        # sku was set to str(variant_id) when building inventory_products,
        # and Etsy echoes it back unchanged -- this is the real mapping
        # order_fulfillment.py needs from a purchased transaction's real
        # product_id back to the correct Printify variant_id.
        variant_map = {
            str(p["product_id"]): int(p["sku"])
            for p in real_products
            if p.get("sku") and str(p["sku"]).isdigit()
        }
        design_brief = dict(product.design_brief or {})
        pod_data = dict(design_brief.get("pod", {}))
        pod_data["variant_map"] = variant_map
        design_brief["pod"] = pod_data
        product.design_brief = design_brief
        self.db.commit()

    def _raise_concern(self, *, summary: str, payload: dict) -> None:
        from app.models.models import Approval
        self.db.add(Approval(
            action_type="operational_concern", summary=summary, payload=payload,
            estimated_cost_usd=0.0, risk_level="medium", requested_by_agent=self.key, status="pending",
        ))
        self.db.commit()
