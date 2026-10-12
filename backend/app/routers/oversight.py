from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.agents.ultron import UltronSupervisorAgent
from app.auth.security import get_current_user
from app.database import get_db
from app.models.models import SupervisionReview

router = APIRouter(prefix="/oversight", tags=["oversight"])


@router.get("/reviews")
def list_reviews(scope: str | None = None, limit: int = 50, db: Session = Depends(get_db), user=Depends(get_current_user)):
    q = db.query(SupervisionReview)
    if scope:
        q = q.filter(SupervisionReview.scope == scope)
    reviews = q.order_by(SupervisionReview.id.desc()).limit(limit).all()
    return [
        {
            "id": r.id, "scope": r.scope, "scope_id": r.scope_id, "verdict": r.verdict,
            "summary": r.summary, "findings": r.findings, "created_at": r.created_at,
        }
        for r in reviews
    ]


@router.get("/reviews/latest-system")
def latest_system_review(db: Session = Depends(get_db), user=Depends(get_current_user)):
    r = (
        db.query(SupervisionReview)
        .filter(SupervisionReview.scope == "system")
        .order_by(SupervisionReview.id.desc())
        .first()
    )
    if not r:
        return None
    return {
        "id": r.id, "verdict": r.verdict, "summary": r.summary,
        "findings": r.findings, "created_at": r.created_at,
    }


@router.post("/system-check")
def run_system_check(db: Session = Depends(get_db), user=Depends(get_current_user)):
    review = UltronSupervisorAgent(db).system_health_check()
    return {
        "id": review.id, "verdict": review.verdict, "summary": review.summary,
        "findings": review.findings, "created_at": review.created_at,
    }
