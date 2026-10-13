"""
POD Production Agent (spec section 10).

Generates real print-ready artwork via AI image generation and creates a
real draft product on Printify to get back real per-variant fulfillment
cost and real mockup images. The Etsy listing itself is still created
through app/integrations/etsy.py and the same owner-approval gate as
digital products -- Printify is used purely as a catalog/fulfillment
backend here, not as the sales channel.

NICHE_CATALOG_MAP entries are real, account-specific Printify catalog IDs,
looked up live against the real catalog (2026-10-13) -- not guessed:
  - T-shirt: blueprint 6 "Unisex Heavy Cotton Tee" (Gildan) x print
    provider 99 "Printify Choice" (Printify's own reliability-balanced
    default across its provider network). Variants: Black + White,
    sizes S-2XL (10 variants).
  - Mug: blueprint 68 "Mug 11oz" x print provider 1 "SPOKE Custom
    Products" (the only print provider for this blueprint). 1 variant
    (11oz, no color/size options).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.agents.base import BaseAgent
from app.config import settings
from app.integrations import printify
from app.integrations.file_storage import product_dir, register_asset
from app.integrations.image_providers import generate_print_artwork
from app.models.models import ProductSpecification

_TSHIRT_CATALOG = {
    "blueprint_id": 6,
    "print_provider_id": 99,
    "variant_ids": [12100, 12101, 12102, 12103, 12104, 12124, 12125, 12126, 12127, 12128],  # White/Black, S-2XL
    "print_position": "front",
}
_MUG_CATALOG = {
    "blueprint_id": 68,
    "print_provider_id": 1,
    "variant_ids": [33719],  # 11oz, only variant
    "print_position": "front",
}

NICHE_CATALOG_MAP: dict[str, dict] = {
    "Faith-Based Graphic T-Shirts": _TSHIRT_CATALOG,
    "Funny Cat-Lover T-Shirts": _TSHIRT_CATALOG,
    "Teacher Appreciation POD Gifts": _TSHIRT_CATALOG,
    "Scripture Verse Coffee Mugs": _MUG_CATALOG,
    "Motivational Quote Mugs": _MUG_CATALOG,
}


def _lookup_catalog(title: str) -> dict | None:
    for niche_title, catalog in NICHE_CATALOG_MAP.items():
        if title.startswith(niche_title):
            return catalog
    return None


def _print_artwork_prompt(product: ProductSpecification) -> str:
    """Standalone graphic design, not a lifestyle photo -- centered subject,
    no legible text (same garbled-text failure mode as listing photos, see
    image_providers.py / digital_production.py), transparent-friendly
    background since it gets placed onto a real garment/mug by Printify."""
    return (
        f"A clean, centered standalone graphic design for printing on a "
        f"physical product, in the theme of '{product.title}', aimed at "
        f"this buyer: {product.target_customer} Bold simple shapes, "
        f"flat illustration style suitable for screen printing, plain "
        f"white or transparent background, no legible text, letters, or "
        f"words anywhere in the image, no logos or brand names."
    )


@dataclass
class PODProductionResult:
    success: bool
    blocked_reason: str | None = None
    printify_product_id: str | None = None
    real_cost_usd: float | None = None
    mockup_image_url: str | None = None
    artwork_png_bytes: bytes | None = None
    image_cost_usd: float = 0.0


class PODProductionAgent(BaseAgent):
    key = "pod_production"

    def produce(self, product: ProductSpecification, workflow_run_id: int | None = None) -> PODProductionResult:
        if not settings.printify_configured:
            return PODProductionResult(False, blocked_reason="Printify not connected (PRINTIFY_API_TOKEN not set in backend/.env).")
        if not settings.printify_shop_id:
            return PODProductionResult(False, blocked_reason="PRINTIFY_SHOP_ID not set in backend/.env.")

        catalog = _lookup_catalog(product.title)
        if not catalog:
            return PODProductionResult(
                False,
                blocked_reason=(
                    f"No verified Printify catalog mapping for '{product.title}' yet "
                    f"(see NICHE_CATALOG_MAP in app/agents/pod_production.py)."
                ),
            )

        artwork = generate_print_artwork(
            self.db,
            agent_key=self.key,
            prompt=_print_artwork_prompt(product),
            title=product.title,
            palette=(product.design_brief or {}).get("palette", {
                "primary": "#1B4332", "secondary": "#40916C", "accent": "#D8F3DC", "text": "#081C15",
            }),
            workflow_run_id=workflow_run_id,
        )
        if artwork.is_mock:
            return PODProductionResult(
                False,
                blocked_reason="Real artwork generation unavailable (no OPENAI_API_KEY or the call failed) -- "
                               "refusing to submit a placeholder design as real print artwork.",
            )

        upload = printify.upload_image(f"product_{product.id}_artwork.png", image_bytes=artwork.png_bytes)
        image_id = upload.get("id")
        if not image_id:
            return PODProductionResult(False, blocked_reason=f"Printify image upload did not return an id: {upload}")

        result = printify.create_product(
            settings.printify_shop_id,
            title=product.title,
            description=product.problem_solved,
            blueprint_id=catalog["blueprint_id"],
            print_provider_id=catalog["print_provider_id"],
            variant_ids=catalog["variant_ids"],
            price_usd=product.recommended_price_usd,
            image_id=image_id,
            print_position=catalog.get("print_position", "front"),
        )
        if not result.success:
            return PODProductionResult(False, blocked_reason=result.detail)

        real_cost = max(result.variant_costs_usd.values()) if result.variant_costs_usd else None

        # Persist the real artwork as a real local asset (same pattern as
        # digital products) so QA/Psalm 90:17's "assets present on disk"
        # check applies uniformly, and so the actual print file is kept.
        artwork_path = product_dir(product.id) / f"artwork_{product.id}.png"
        artwork_path.write_bytes(artwork.png_bytes)
        register_asset(self.db, product.id, "png", artwork_path)

        # Real financial data: replace the $11 placeholder estimate from
        # product_strategy.py with the real Printify-quoted cost now that
        # it's known.
        design_brief = dict(product.design_brief or {})
        design_brief["pod"] = {
            "printify_product_id": result.product_id,
            "real_cost_usd": real_cost,
            "mockup_image_url": result.mockup_image_urls[0] if result.mockup_image_urls else None,
            "blueprint_id": catalog["blueprint_id"],
            "print_provider_id": catalog["print_provider_id"],
        }
        product.design_brief = design_brief
        if real_cost is not None:
            product.estimated_cost_usd = real_cost
            product.estimated_margin_usd = round(product.recommended_price_usd - real_cost, 2)
        self.db.commit()

        self.log(
            "pod_product_created",
            f"Printify draft product #{result.product_id} created for product #{product.id} "
            f"(real cost ${real_cost if real_cost is not None else 'unknown'})",
            {"product_id": product.id, "printify_product_id": result.product_id, "real_cost_usd": real_cost},
        )
        return PODProductionResult(
            True,
            printify_product_id=result.product_id,
            real_cost_usd=real_cost,
            mockup_image_url=result.mockup_image_urls[0] if result.mockup_image_urls else None,
            artwork_png_bytes=artwork.png_bytes,
            image_cost_usd=artwork.cost_usd,
        )
