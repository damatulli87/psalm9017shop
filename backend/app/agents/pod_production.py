"""
POD Production Agent (spec section 10).

Generates real print-ready artwork via AI image generation and creates a
real draft product on Printify to get back real per-variant fulfillment
cost and real mockup images. The Etsy listing itself is still created
through app/integrations/etsy.py and the same owner-approval gate as
digital products -- Printify is used purely as a catalog/fulfillment
backend here, not as the sales channel.

NICHE_CATALOG_MAP is intentionally empty. Each entry is real,
account-specific Printify catalog data (a blueprint_id + print_provider_id
+ variant_ids combination that actually exists and prints the intended
physical product) -- not something safe to guess or hardcode ahead of a
real catalog lookup. Until a niche has a verified entry here, production
for it stays blocked with an honest reason rather than silently using a
wrong or made-up catalog ID. Fill this in via scripts/printify_catalog.py
(or an equivalent one-off lookup) once PRINTIFY_API_TOKEN is configured.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.agents.base import BaseAgent
from app.config import settings
from app.integrations import printify
from app.integrations.image_providers import generate_print_artwork
from app.models.models import ProductSpecification

NICHE_CATALOG_MAP: dict[str, dict] = {
    # "Faith-Based Graphic T-Shirts": {
    #     "blueprint_id": 0, "print_provider_id": 0, "variant_ids": [0], "print_position": "front",
    # },
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
