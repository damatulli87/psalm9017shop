"""
OAuth connect/callback routes for marketplace integrations. The PKCE code
verifier only needs to survive the few seconds between /connect and
/callback, so an in-process dict is sufficient for this single-instance
app (documented limitation: a restart mid-flow just means the owner clicks
Connect again).
"""
from __future__ import annotations

import secrets
import time

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth.security import get_current_user
from app.config import settings
from app.database import get_db
from app.integrations import etsy, oauth_store
from app.models.models import AuditEvent

router = APIRouter(prefix="/integrations", tags=["integrations"])

_PENDING_STATE_TTL_SECONDS = 600
_pending_states: dict[str, tuple[str, float]] = {}  # state -> (code_verifier, created_at)


def _cleanup_pending_states() -> None:
    cutoff = time.time() - _PENDING_STATE_TTL_SECONDS
    for state in [s for s, (_, created) in _pending_states.items() if created < cutoff]:
        _pending_states.pop(state, None)


@router.get("/etsy/connect")
def etsy_connect():
    # Deliberately NOT behind get_current_user: this is a full-page browser
    # redirect (Etsy's consent screen -> our callback), which can't carry a
    # bearer header. Etsy's own login/consent screen is the real gate on
    # who can complete the flow. Acceptable for a single-owner local app;
    # add session-cookie protection here before any internet-exposed
    # deployment (see SECURITY.md).
    if not settings.etsy_configured:
        raise HTTPException(
            status_code=400,
            detail="Set ETSY_API_KEY, ETSY_API_SECRET, and ETSY_SHOP_ID in backend/.env and restart before connecting.",
        )
    _cleanup_pending_states()
    verifier, challenge = etsy.build_pkce_pair()
    state = secrets.token_urlsafe(24)
    _pending_states[state] = (verifier, time.time())
    return RedirectResponse(etsy.get_authorize_url(state, challenge))


@router.get("/etsy/callback")
def etsy_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    if error:
        return RedirectResponse(f"{settings.frontend_base_url}/marketplace?etsy=error&detail={error}")

    pending = _pending_states.pop(state, None) if state else None
    if not pending or not code:
        return RedirectResponse(f"{settings.frontend_base_url}/marketplace?etsy=error&detail=invalid_or_expired_state")

    verifier, _ = pending
    try:
        token_response = etsy.exchange_code_for_token(code, verifier)
        oauth_store.save_token(db, "etsy", token_response)
    except Exception as exc:  # noqa: BLE001
        db.add(AuditEvent(event_type="etsy_oauth_failed", actor="integrations", summary=str(exc)))
        db.commit()
        return RedirectResponse(f"{settings.frontend_base_url}/marketplace?etsy=error&detail=token_exchange_failed")

    db.add(AuditEvent(event_type="etsy_connected", actor="integrations", summary="Etsy OAuth connected successfully."))
    db.commit()
    return RedirectResponse(f"{settings.frontend_base_url}/marketplace?etsy=connected")


@router.post("/etsy/disconnect")
def etsy_disconnect(db: Session = Depends(get_db), user=Depends(get_current_user)):
    oauth_store.disconnect(db, "etsy")
    db.add(AuditEvent(event_type="etsy_disconnected", actor=user.email, summary="Owner disconnected Etsy."))
    db.commit()
    return {"status": "disconnected"}
