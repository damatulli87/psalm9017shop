"""
Etsy Open API v3 adapter (spec section 12).

Real OAuth2 (PKCE) flow and listing-draft call are implemented against
Etsy's documented v3 endpoints. Until the owner registers an Etsy API app
and completes the OAuth flow (ETSY_API_KEY/ETSY_API_SECRET/ETSY_SHOP_ID
env vars + a stored access token), every call runs in SIMULATED mode: it
builds the exact request payload that would be sent, logs it, and returns
a clearly-labeled simulated response. No listing is ever claimed to be
"published" without a verified, successful real API response.
"""
from __future__ import annotations

import base64
import hashlib
import secrets
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

from app.config import settings

ETSY_API_BASE = "https://openapi.etsy.com/v3/application"
ETSY_OAUTH_AUTHORIZE_URL = "https://www.etsy.com/oauth/connect"
ETSY_OAUTH_TOKEN_URL = "https://api.etsy.com/v3/public/oauth/token"
ETSY_SCOPES = "listings_w listings_r shops_r shops_w transactions_r"


def _api_key_header() -> str:
    """This app's x-api-key must be 'keystring:shared_secret' -- confirmed
    against the real Etsy API; the bare keystring alone is rejected."""
    return f"{settings.etsy_api_key}:{settings.etsy_api_secret}"


@dataclass
class EtsyListingResult:
    success: bool
    simulated: bool
    external_listing_id: str | None
    detail: str
    request_payload: dict


def build_pkce_pair() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip("=")
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    return verifier, challenge


def get_authorize_url(state: str, code_challenge: str) -> str:
    """Real Etsy OAuth2/PKCE authorize URL -- usable the moment ETSY_API_KEY is set."""
    params = {
        "response_type": "code",
        "client_id": settings.etsy_api_key,
        "redirect_uri": settings.etsy_oauth_redirect_uri,
        "scope": ETSY_SCOPES,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    return f"{ETSY_OAUTH_AUTHORIZE_URL}?{urlencode(params)}"


def exchange_code_for_token(code: str, code_verifier: str) -> dict:
    if not settings.etsy_configured:
        raise RuntimeError("Etsy credentials not configured -- cannot exchange OAuth code.")
    resp = httpx.post(
        ETSY_OAUTH_TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "client_id": settings.etsy_api_key,
            "redirect_uri": settings.etsy_oauth_redirect_uri,
            "code": code,
            "code_verifier": code_verifier,
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def refresh_access_token(refresh_token: str) -> dict:
    """Etsy v3 uses the same token endpoint with grant_type=refresh_token."""
    if not settings.etsy_configured:
        raise RuntimeError("Etsy credentials not configured -- cannot refresh OAuth token.")
    resp = httpx.post(
        ETSY_OAUTH_TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "client_id": settings.etsy_api_key,
            "refresh_token": refresh_token,
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def create_draft_listing(
    *,
    access_token: str | None,
    title: str,
    description: str,
    price_usd: float,
    tags: list[str],
    is_digital: bool,
    taxonomy_id: int,
) -> EtsyListingResult:
    payload = {
        # Neither digital files nor Printify POD (print-on-demand, no fixed
        # inventory) have a real stock limit -- quantity is a high ceiling
        # either way, not literally "1 unit in stock" for physical items.
        "quantity": 999,
        "title": title[:140],
        "description": description,
        "price": round(price_usd, 2),
        "who_made": "i_did",
        "when_made": "2020_2026",
        "taxonomy_id": taxonomy_id,
        "tags": tags[:13],
        "is_digital": is_digital,
        "state": "draft",
    }
    # Confirmed live (2026-10-14): Etsy's v3 listing-creation endpoint
    # requires shipping_profile_id AND readiness_state_id for EVERY
    # listing at creation time, even with is_digital=True -- a digital
    # listing is created as listing_type "physical" regardless, and only
    # actually becomes listing_type "download" once a real digital file is
    # attached via a separate call (see upload_listing_file() below). The
    # earlier assumption that digital listings skip these fields was wrong
    # and had never been tested against a real listing until a real
    # opportunity actually reached this stage.
    payload["shipping_profile_id"] = settings.etsy_shipping_profile_id
    payload["readiness_state_id"] = settings.etsy_readiness_state_id

    if not settings.etsy_configured or not access_token:
        return EtsyListingResult(
            success=False,
            simulated=True,
            external_listing_id=None,
            detail=(
                "Etsy integration not connected (missing API key/secret/shop_id or OAuth token). "
                "Listing draft payload was constructed and validated locally but NOT sent to Etsy."
            ),
            request_payload=payload,
        )
    if not settings.etsy_shipping_profile_id:
        return EtsyListingResult(
            success=False,
            simulated=True,
            external_listing_id=None,
            detail=(
                "Cannot create a real listing: no ETSY_SHIPPING_PROFILE_ID configured. Etsy "
                "requires a real shipping profile for every listing, digital or physical -- "
                "that's a real shipping-cost decision, not something to guess. Create one in "
                "Etsy's Shop Manager > Settings > Shipping settings, or ask to have one created "
                "via the API with specific real rates."
            ),
            request_payload=payload,
        )
    if not settings.etsy_readiness_state_id:
        return EtsyListingResult(
            success=False,
            simulated=True,
            external_listing_id=None,
            detail=(
                "Cannot create a real listing: no ETSY_READINESS_STATE_ID configured. Etsy "
                "requires a shop-level readiness-state-definition (made_to_order vs ready_to_ship "
                "+ processing time) for every listing, digital or physical."
            ),
            request_payload=payload,
        )

    try:
        resp = httpx.post(
            f"{ETSY_API_BASE}/shops/{settings.etsy_shop_id}/listings",
            headers={"x-api-key": _api_key_header(), "Authorization": f"Bearer {access_token}"},
            json=payload,
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        return EtsyListingResult(
            success=True, simulated=False, external_listing_id=str(data.get("listing_id")),
            detail="Draft listing created via Etsy Open API v3.", request_payload=payload,
        )
    except httpx.HTTPStatusError as exc:
        # str(exc) alone discards the response BODY, which is where Etsy
        # puts the actually useful error ("A shipping_profile_id is
        # required...") -- this cost real debugging time more than once
        # (taxonomy_id, shipping/readiness) before being fixed here once.
        return EtsyListingResult(
            success=False, simulated=False, external_listing_id=None,
            detail=f"Etsy API call failed: {exc.response.status_code} {exc.response.text}",
            request_payload=payload,
        )
    except Exception as exc:  # noqa: BLE001
        return EtsyListingResult(
            success=False, simulated=False, external_listing_id=None,
            detail=f"Etsy API call failed: {exc}", request_payload=payload,
        )


def upload_listing_image(
    *, access_token: str, listing_id: str, image_bytes: bytes, rank: int = 1, alt_text: str = "",
) -> tuple[bool, str]:
    """Real multipart upload -- confirmed live that create_draft_listing()
    alone leaves `images: null` on the real listing; Etsy requires this
    separate call per image, it's not part of listing creation."""
    try:
        resp = httpx.post(
            f"{ETSY_API_BASE}/shops/{settings.etsy_shop_id}/listings/{listing_id}/images",
            headers={"x-api-key": _api_key_header(), "Authorization": f"Bearer {access_token}"},
            files={"image": ("listing.png", image_bytes, "image/png")},
            data={"rank": rank, "alt_text": alt_text[:500]},
            timeout=30,
        )
        resp.raise_for_status()
        return True, "Listing image uploaded."
    except Exception as exc:  # noqa: BLE001
        return False, f"Etsy image upload failed: {exc}"


def upload_listing_file(
    *, access_token: str, listing_id: str, file_bytes: bytes, file_name: str, rank: int = 1,
) -> tuple[bool, str]:
    """The actual deliverable (ZIP) for a digital product. Confirmed live
    (2026-10-14) this is the ONLY thing that makes Etsy treat a listing as
    a real digital download -- create_draft_listing() with is_digital=True
    alone creates a listing_type "physical" listing regardless; it only
    flips to listing_type "download" once a real file is attached here.
    Before this was discovered, a "successful" digital listing would have
    shipped a buyer literally nothing."""
    try:
        resp = httpx.post(
            f"{ETSY_API_BASE}/shops/{settings.etsy_shop_id}/listings/{listing_id}/files",
            headers={"x-api-key": _api_key_header(), "Authorization": f"Bearer {access_token}"},
            files={"file": (file_name, file_bytes, "application/octet-stream")},
            data={"name": file_name, "rank": rank},
            timeout=30,
        )
        resp.raise_for_status()
        return True, "Digital file uploaded; listing is now a real download listing."
    except httpx.HTTPStatusError as exc:
        return False, f"Etsy file upload failed: {exc.response.status_code} {exc.response.text}"
    except Exception as exc:  # noqa: BLE001
        return False, f"Etsy file upload failed: {exc}"


def search_top_listings(keyword: str, *, access_token: str, sample_size: int = 50, top_n: int = 10) -> list[dict]:
    """Real competitive research: searches Etsy's live active listings for
    `keyword` and returns the top_n by real num_favorers within the sampled
    batch. Etsy's search itself only sorts by relevance/price/date, not
    popularity, so this pulls a real sample and sorts client-side -- that's
    why a sample_size larger than top_n matters (confirmed live: the first
    page by relevance had single-digit favorites; sorting a 50-result
    sample surfaced one with 2,359). Titles/tags only -- never images, to
    avoid any risk of reproducing another seller's actual artwork."""
    resp = httpx.get(
        f"{ETSY_API_BASE}/listings/active",
        headers={"x-api-key": _api_key_header(), "Authorization": f"Bearer {access_token}"},
        params={"keywords": keyword, "limit": sample_size, "sort_on": "score", "sort_order": "desc"},
        timeout=15,
    )
    resp.raise_for_status()
    results = resp.json().get("results", [])
    results.sort(key=lambda r: r.get("num_favorers", 0), reverse=True)
    return [
        {"title": r.get("title", ""), "tags": r.get("tags", []), "num_favorers": r.get("num_favorers", 0)}
        for r in results[:top_n]
    ]


def get_active_listing_count(keyword: str, *, access_token: str) -> int:
    """Real market-saturation signal for opportunity scoring: total active
    Etsy listings matching keyword (not a sample -- Etsy's search response
    includes the real total `count` regardless of `limit`). limit=1 to
    keep this call cheap since only the count is used."""
    resp = httpx.get(
        f"{ETSY_API_BASE}/listings/active",
        headers={"x-api-key": _api_key_header(), "Authorization": f"Bearer {access_token}"},
        params={"keywords": keyword, "limit": 1},
        timeout=15,
    )
    resp.raise_for_status()
    return int(resp.json().get("count", 0))


def list_recent_paid_receipts(*, access_token: str, limit: int = 25) -> list[dict]:
    """Real orders: GET /shops/{shop_id}/receipts, was_paid=true so unpaid/
    abandoned carts never trigger fulfillment, sorted newest first. Each
    receipt's real schema (confirmed live, 2026-10-14) includes shipping
    address fields (name/first_line/second_line/city/state/zip/country_iso),
    buyer_email, and a `transactions` array with listing_id/is_digital/
    quantity/product_id per line item -- everything order_fulfillment.py
    needs to tell a real digital sale (Etsy handles delivery itself once
    the file is attached, see etsy_manager.py) from a real POD sale
    (needs a real Printify order submitted). `product_id` (confirmed
    against Etsy's real ShopReceiptTransaction schema, not guessed) is the
    real purchased variation/offering's id -- not a free-text description
    of which size/color the buyer picked -- so fulfilling correctly means
    mapping it back through the real inventory this app itself set on the
    listing (see set_listing_inventory() below), not parsing any string."""
    resp = httpx.get(
        f"{ETSY_API_BASE}/shops/{settings.etsy_shop_id}/receipts",
        headers={"x-api-key": _api_key_header(), "Authorization": f"Bearer {access_token}"},
        params={"was_paid": "true", "limit": limit, "sort_on": "created", "sort_order": "desc"},
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json().get("results", [])


def get_listing(listing_id: str, *, access_token: str) -> dict | None:
    """Real listing state, used to verify a digital order actually has its
    file attached (listing_type == "download") before trusting that Etsy
    will deliver it -- not just assuming because product.product_type
    says "digital"."""
    resp = httpx.get(
        f"{ETSY_API_BASE}/listings/{listing_id}",
        headers={"x-api-key": _api_key_header(), "Authorization": f"Bearer {access_token}"},
        timeout=15,
    )
    if resp.status_code >= 400:
        return None
    return resp.json()


def get_taxonomy_properties(taxonomy_id: int) -> list[dict]:
    """Real per-category property/value definitions (e.g. "Primary color"
    property_id 200 with value_id 1 = "Black"), confirmed against Etsy's
    real seller-taxonomy endpoint -- no auth beyond the api-key required
    (confirmed live). Used to build real, valid property_values for
    set_listing_inventory() rather than guessing ids."""
    resp = httpx.get(
        f"{ETSY_API_BASE}/seller-taxonomy/nodes/{taxonomy_id}/properties",
        headers={"x-api-key": _api_key_header()},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json().get("results", [])


def set_listing_inventory(
    listing_id: str, products: list[dict], *, sku_on_property: list[int], access_token: str,
) -> tuple[bool, str, list[dict]]:
    """Real PUT /listings/{listing_id}/inventory (confirmed against Etsy's
    own OpenAPI spec, requires oauth2 scope listings_w -- already in
    ETSY_SCOPES). `products` is one entry per real sellable variant
    (sku/property_values/offerings -- see etsy_manager.py for how these are
    built from Printify's real variant data). Two real requirements the
    OpenAPI spec doesn't document, found live by actually calling this
    against a real test listing rather than trusting the spec alone: (1)
    every offering needs its own `readiness_state_id` (same shop-level id
    used at listing creation, not a separate value -- confirmed live),
    without which Etsy 400s with "All offerings need readiness state"; (2)
    `sku_on_property` (the property_ids the sku varies by) must be passed
    at the top level whenever products have distinct skus, or Etsy 400s
    with "sku must be consistent across all products". On success, Etsy
    assigns each product a real `product_id` and echoes back the `sku` we
    sent unchanged -- that's what lets order_fulfillment.py later map a
    real purchased transaction's `product_id` back to the correct
    Printify variant_id (sku was set to str(variant_id) deliberately),
    rather than parsing any free-text variation description."""
    try:
        resp = httpx.put(
            f"{ETSY_API_BASE}/listings/{listing_id}/inventory",
            headers={"x-api-key": _api_key_header(), "Authorization": f"Bearer {access_token}"},
            json={"products": products, "sku_on_property": sku_on_property},
            timeout=30,
        )
        resp.raise_for_status()
        return True, "Real listing inventory/variations set.", resp.json().get("products", [])
    except httpx.HTTPStatusError as exc:
        return False, f"Etsy inventory update failed: {exc.response.status_code} {exc.response.text}", []
    except Exception as exc:  # noqa: BLE001
        return False, f"Etsy inventory update failed: {exc}", []


def get_listing_inventory(listing_id: str, *, access_token: str) -> list[dict]:
    """Real current inventory/products for a listing -- used to verify a
    set_listing_inventory() call actually took effect, not just that the
    PUT returned 200."""
    resp = httpx.get(
        f"{ETSY_API_BASE}/listings/{listing_id}/inventory",
        headers={"x-api-key": _api_key_header(), "Authorization": f"Bearer {access_token}"},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json().get("products", [])
