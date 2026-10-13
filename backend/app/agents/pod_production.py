"""
POD Production Agent (spec section 10).

Generates real print-ready artwork via AI image generation and creates a
real draft product on Printify to get back real per-variant fulfillment
cost and real mockup images. The Etsy listing itself is still created
through app/integrations/etsy.py and the same owner-approval gate as
digital products -- Printify is used purely as a catalog/fulfillment
backend here, not as the sales channel.

NICHE_CATALOG_MAP entries are real, account-specific Printify catalog IDs,
looked up live against the real catalog (2026-10-13) -- not guessed, and
each product type's real fulfillment cost was verified with an actual
create_product() call before being priced in product_strategy.py:
  - T-shirt: blueprint 6 "Unisex Heavy Cotton Tee" (Gildan) x print
    provider 99 "Printify Choice". Black+White, S-2XL (10 variants).
    Real cost: $9.68-$11.77.
  - Mug: blueprint 68 "Mug 11oz" x print provider 1 "SPOKE Custom
    Products" (only provider for this blueprint). 1 variant. Real cost:
    $6.44.
  - Hoodie: blueprint 175 "Unisex Sponge Fleece Pullover Hoodie"
    (Bella+Canvas) x print provider 99 "Printify Choice". Black+White,
    S-2XL (10 variants). Real cost: $37.55-$40.84. Considered switching
    to a cheaper Gildan blank (blueprint 1525, ~$27 real cost) when the
    owner asked about cheaper hoodie options, but the owner then
    clarified comfort/quality mattered more than lowest cost --
    Bella+Canvas is consistently the most-cited "soft, quality blank"
    pick in POD-seller comparisons (combed ring-spun cotton), so kept
    the original choice rather than trading quality for margin.
  - Tote bag: blueprint 507 "Canvas Tote Bag, 5-Color Straps" x print
    provider 99 "Printify Choice". Black+White, both sizes (4 variants).
    Real cost: $18.74-$20.05.
  - Stickers: blueprint 400 "Kiss-Cut Stickers" x print provider 99
    "Printify Choice". All 4 sizes (2"/3"/4"/6"). Real cost: $1.42-$2.32.
  - Cap: blueprint 1108 "Low Profile Baseball Cap" x print provider 99
    "Printify Choice", DTF print at "front" (this blueprint also has
    embroidery-only placeholders -- "front" specifically is the one
    print-based area). 6 colors, one size. Real cost: $15.38.
  - Necklace: blueprint 778 "Oval Necklace" x print provider 99
    "Printify Choice", dye-sublimation. 1 variant (Silver, one size).
    Confirmed this blueprint accepts a full-color image print (not
    engraving-only, which would need very different artwork). Real
    cost: $13.47.
  - Notebook: blueprint 1931 "Hardcover Bound Notebook" x print
    provider 99 "Printify Choice". Real placeholder position is
    "front_uv" (uv-print), NOT "front" -- a plain "front" call failed
    with a 422 until this was looked up from the real variants
    response. 8 colors. Real cost: $15.63.
  - Tumbler: blueprint 353 "Tumbler 20oz" x print provider 1 "SPOKE
    Custom Products" (only provider), dye-sublimation. 1 variant. Real
    cost: $24.97.
"Printify Choice" was used for every type that offers it, for
consistency -- it's Printify's own reliability-balanced default across
its provider network, not a guess specific to one product. The real
placeholder `position` name is looked up per blueprint+provider from
its /variants.json response (`placeholders[].position`), not assumed to
be "front" -- the notebook case above is exactly why.
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
_HOODIE_CATALOG = {
    "blueprint_id": 175,
    "print_provider_id": 99,
    "variant_ids": [39826, 39844, 39862, 39880, 39898, 39838, 39856, 39874, 39892, 39910],  # Black/White, S-2XL
    "print_position": "front",
}
_TOTE_CATALOG = {
    "blueprint_id": 507,
    "print_provider_id": 99,
    "variant_ids": [80815, 80818, 80820, 80823],  # Black/White, 13x13 & 16x16
    "print_position": "front",
}
_STICKER_CATALOG = {
    "blueprint_id": 400,
    "print_provider_id": 99,
    "variant_ids": [45748, 45750, 45752, 45754],  # 2"/3"/4"/6"
    "print_position": "front",
}
_CAP_CATALOG = {
    "blueprint_id": 1108,
    "print_provider_id": 99,
    "variant_ids": [82433, 82434, 104278, 104279, 104280, 104282],  # 6 colors, one size
    "print_position": "front",
}
_NECKLACE_CATALOG = {
    "blueprint_id": 778,
    "print_provider_id": 99,
    "variant_ids": [74660],  # Silver, one size
    "print_position": "front",
}
_NOTEBOOK_CATALOG = {
    "blueprint_id": 1931,
    "print_provider_id": 99,
    "variant_ids": [119669, 119670, 119671, 119672, 119673, 119674, 119675, 119676],  # 8 colors
    "print_position": "front_uv",
}
_TUMBLER_CATALOG = {
    "blueprint_id": 353,
    "print_provider_id": 1,
    "variant_ids": [44519],  # 20oz, only variant
    "print_position": "front",
}

NICHE_CATALOG_MAP: dict[str, dict] = {
    "Faith-Based Graphic T-Shirts": _TSHIRT_CATALOG,
    "Funny Cat-Lover T-Shirts": _TSHIRT_CATALOG,
    "Teacher Appreciation POD Gifts": _TSHIRT_CATALOG,
    "Nurse Appreciation T-Shirts": _TSHIRT_CATALOG,
    "Scripture Verse Coffee Mugs": _MUG_CATALOG,
    "Motivational Quote Mugs": _MUG_CATALOG,
    "Zodiac Sign Coffee Mugs": _MUG_CATALOG,
    "Christian Faith Pullover Hoodies": _HOODIE_CATALOG,
    "Dog Mom Pullover Hoodies": _HOODIE_CATALOG,
    "Wedding Party Tote Bags": _TOTE_CATALOG,
    "Teacher Appreciation Tote Bags": _TOTE_CATALOG,
    "Motivational Quote Sticker Packs": _STICKER_CATALOG,
    "Christian Faith Sticker Packs": _STICKER_CATALOG,
    "Christian Faith Baseball Caps": _CAP_CATALOG,
    "Faith Cross Necklaces": _NECKLACE_CATALOG,
    "Daily Gratitude Journal Notebooks": _NOTEBOOK_CATALOG,
    "Motivational Quote Tumblers": _TUMBLER_CATALOG,
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
