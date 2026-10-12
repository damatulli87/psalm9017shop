from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.security import get_current_user
from app.database import get_db
from app.models.models import AuditEvent

router = APIRouter(prefix="/activity", tags=["activity"])


@router.get("")
def list_activity(limit: int = 100, db: Session = Depends(get_db), user=Depends(get_current_user)):
    events = db.query(AuditEvent).order_by(AuditEvent.id.desc()).limit(limit).all()
    return [
        {"id": e.id, "event_type": e.event_type, "actor": e.actor, "summary": e.summary,
         "created_at": e.created_at, "payload": e.payload}
        for e in events
    ]
