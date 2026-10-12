"""
Persists and retrieves OAuth tokens, transparently refreshing expired
Etsy tokens. This is the only module that reads/writes OAuthToken rows --
everything else that needs a live access token calls get_valid_etsy_token().
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.integrations import crypto, etsy
from app.models.models import IntegrationCredential, OAuthToken, Storefront

REFRESH_MARGIN = timedelta(minutes=5)


def save_token(db: Session, provider: str, token_response: dict) -> OAuthToken:
    expires_in = token_response.get("expires_in")
    expires_at = (
        datetime.now(timezone.utc) + timedelta(seconds=int(expires_in)) if expires_in is not None else None
    )

    row = db.query(OAuthToken).filter(OAuthToken.provider == provider).first()
    if row is None:
        row = OAuthToken(provider=provider, access_token_encrypted="")
        db.add(row)

    row.access_token_encrypted = crypto.encrypt(token_response["access_token"])
    if token_response.get("refresh_token"):
        row.refresh_token_encrypted = crypto.encrypt(token_response["refresh_token"])
    row.scope = token_response.get("scope", "")
    row.expires_at = expires_at
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)

    cred = db.query(IntegrationCredential).filter(IntegrationCredential.provider == provider).first()
    if cred:
        cred.status = "connected"
        cred.last_verified_at = datetime.now(timezone.utc)

    sf = db.query(Storefront).filter(Storefront.channel == provider).first()
    if sf:
        sf.connected = True
        sf.status_detail = "connected"
        sf.connected_at = datetime.now(timezone.utc)

    db.commit()
    return row


def get_valid_etsy_token(db: Session) -> str | None:
    row = db.query(OAuthToken).filter(OAuthToken.provider == "etsy").first()
    if row is None:
        return None

    if row.expires_at and datetime.now(timezone.utc) + REFRESH_MARGIN >= row.expires_at:
        if not row.refresh_token_encrypted:
            return None  # expired with no way to refresh; owner must reconnect
        try:
            refreshed = etsy.refresh_access_token(crypto.decrypt(row.refresh_token_encrypted))
        except Exception:  # noqa: BLE001
            return None
        row = save_token(db, "etsy", refreshed)

    return crypto.decrypt(row.access_token_encrypted)


def disconnect(db: Session, provider: str) -> None:
    row = db.query(OAuthToken).filter(OAuthToken.provider == provider).first()
    if row:
        db.delete(row)
    cred = db.query(IntegrationCredential).filter(IntegrationCredential.provider == provider).first()
    if cred:
        cred.status = "not_configured"
        cred.last_verified_at = None
    sf = db.query(Storefront).filter(Storefront.channel == provider).first()
    if sf:
        sf.connected = False
        sf.status_detail = "not_configured"
    db.commit()
