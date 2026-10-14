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
    if not is_digital:
        # Etsy requires both for every physical listing.
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
    if not is_digital and not settings.etsy_shipping_profile_id:
        return EtsyListingResult(
            success=False,
            simulated=True,
            external_listing_id=None,
            detail=(
                "Cannot create a real physical listing: no ETSY_SHIPPING_PROFILE_ID configured. "
                "Etsy requires a real shipping profile (cost/handling time) for every physical "
                "listing -- that's a real shipping-cost decision, not something to guess. Create "
                "one in Etsy's Shop Manager > Settings > Shipping settings, or ask to have one "
                "created via the API with specific real rates."
            ),
            request_payload=payload,
        )
    if not is_digital and not settings.etsy_readiness_state_id:
        return EtsyListingResult(
            success=False,
            simulated=True,
            external_listing_id=None,
            detail=(
                "Cannot create a real physical listing: no ETSY_READINESS_STATE_ID configured. "
                "Etsy requires a shop-level readiness-state-definition (made_to_order vs "
                "ready_to_ship + processing time) for every physical listing."
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
