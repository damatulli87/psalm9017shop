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
ETSY_SCOPES = "listings_w listings_r shops_r transactions_r"


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
) -> EtsyListingResult:
    payload = {
        "quantity": 999 if is_digital else 1,
        "title": title[:140],
        "description": description,
        "price": round(price_usd, 2),
        "who_made": "i_did",
        "when_made": "2020_2026",
        "taxonomy_id": 0,
        "tags": tags[:13],
        "is_digital": is_digital,
        "state": "draft",
    }

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

    try:
        resp = httpx.post(
            f"{ETSY_API_BASE}/shops/{settings.etsy_shop_id}/listings",
            headers={"x-api-key": settings.etsy_api_key, "Authorization": f"Bearer {access_token}"},
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
