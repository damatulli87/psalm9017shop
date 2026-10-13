"""
Printify API v1 adapter (print-on-demand fulfillment for physical products:
t-shirts, mugs, etc).

Printify is used purely as a catalog/fulfillment backend here, not as the
sales channel -- Etsy listings for POD products still go through our own
app/integrations/etsy.py and the same owner-approval gate as digital
products, so there is one unified place real listings get created and
approved, not two. Printify's own direct-publish-to-Etsy feature is
intentionally not used.

Every call requires a real PRINTIFY_API_TOKEN (generated at
https://printify.com/app/account/api). There is no "simulated mode" here
the way etsy.py has one, because there's nothing useful to simulate: catalog
IDs (blueprint/print_provider/variant) are account- and catalog-specific
real data, not something safe to guess or hardcode -- see PROGRESS.md for
the real blueprint/variant IDs once they're looked up against the real
catalog.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass, field

import httpx

from app.config import settings

PRINTIFY_API_BASE = "https://api.printify.com/v1"
USER_AGENT = "Psalm90-17Commerce/1.0 (+https://github.com/damatulli87/psalm9017shop)"


class PrintifyNotConfigured(RuntimeError):
    pass


def _headers() -> dict:
    if not settings.printify_configured:
        raise PrintifyNotConfigured("PRINTIFY_API_TOKEN not set in backend/.env.")
    return {
        "Authorization": f"Bearer {settings.printify_api_token}",
        "User-Agent": USER_AGENT,
        "Content-Type": "application/json;charset=utf-8",
    }


def list_shops() -> list[dict]:
    resp = httpx.get(f"{PRINTIFY_API_BASE}/shops.json", headers=_headers(), timeout=15)
    resp.raise_for_status()
    return resp.json()


def list_blueprints() -> list[dict]:
    resp = httpx.get(f"{PRINTIFY_API_BASE}/catalog/blueprints.json", headers=_headers(), timeout=15)
    resp.raise_for_status()
    return resp.json()


def get_blueprint(blueprint_id: int) -> dict:
    resp = httpx.get(f"{PRINTIFY_API_BASE}/catalog/blueprints/{blueprint_id}.json", headers=_headers(), timeout=15)
    resp.raise_for_status()
    return resp.json()


def get_print_providers(blueprint_id: int) -> list[dict]:
    resp = httpx.get(
        f"{PRINTIFY_API_BASE}/catalog/blueprints/{blueprint_id}/print_providers.json",
        headers=_headers(), timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def get_variants(blueprint_id: int, print_provider_id: int) -> list[dict]:
    """Real per-variant data from the catalog, including size/color options.
    Note: the catalog response does not include real fulfillment cost --
    that only comes back on the product object after create_product()."""
    resp = httpx.get(
        f"{PRINTIFY_API_BASE}/catalog/blueprints/{blueprint_id}/print_providers/{print_provider_id}/variants.json",
        headers=_headers(), timeout=15,
    )
    resp.raise_for_status()
    return resp.json().get("variants", [])


def upload_image(file_name: str, *, image_bytes: bytes) -> dict:
    """Uploads via base64 (image_bytes) -- fine for our generated artwork,
    which is well under Printify's 5MB base64 recommendation ceiling."""
    payload = {"file_name": file_name, "contents": base64.b64encode(image_bytes).decode()}
    resp = httpx.post(f"{PRINTIFY_API_BASE}/uploads/images.json", headers=_headers(), json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()


@dataclass
class PrintifyProductResult:
    success: bool
    product_id: str | None
    variant_costs_usd: dict[str, float] = field(default_factory=dict)  # variant_id -> real fulfillment cost
    mockup_image_urls: list[str] = field(default_factory=list)
    detail: str = ""
    raw: dict = field(default_factory=dict)


def create_product(
    shop_id: str,
    *,
    title: str,
    description: str,
    blueprint_id: int,
    print_provider_id: int,
    variant_ids: list[int],
    price_usd: float,
    image_id: str,
    print_position: str = "front",
) -> PrintifyProductResult:
    """Creates a draft product (not published anywhere) purely to get back
    real per-variant fulfillment cost and real mockup images -- the actual
    Etsy listing is created separately via app/integrations/etsy.py."""
    payload = {
        "title": title[:255],
        "description": description,
        "blueprint_id": blueprint_id,
        "print_provider_id": print_provider_id,
        "variants": [{"id": vid, "price": round(price_usd * 100), "is_enabled": True} for vid in variant_ids],
        "print_areas": [
            {
                "variant_ids": variant_ids,
                "placeholders": [
                    {
                        "position": print_position,
                        "images": [{"id": image_id, "x": 0.5, "y": 0.5, "scale": 1.0, "angle": 0}],
                    }
                ],
            }
        ],
    }
    resp = httpx.post(
        f"{PRINTIFY_API_BASE}/shops/{shop_id}/products.json", headers=_headers(), json=payload, timeout=30,
    )
    if resp.status_code >= 400:
        return PrintifyProductResult(
            success=False, product_id=None, detail=f"Printify API error {resp.status_code}: {resp.text[:500]}",
        )
    data = resp.json()
    variant_costs = {
        str(v["id"]): round(v.get("cost", 0) / 100, 2)
        for v in data.get("variants", [])
        if "cost" in v
    }
    mockups = [img["src"] for img in data.get("images", []) if img.get("src")]
    return PrintifyProductResult(
        success=True,
        product_id=str(data.get("id")),
        variant_costs_usd=variant_costs,
        mockup_image_urls=mockups,
        detail="Draft product created on Printify (not published) -- real per-variant cost returned.",
        raw=data,
    )
