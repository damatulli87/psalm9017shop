from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.security import get_current_user
from app.database import get_db
from app.models.models import Approval
from app.orchestration.workflow_engine import resume_after_approval
from app.policy.engine import decide_approval

router = APIRouter(prefix="/approvals", tags=["approvals"])


class DecisionRequest(BaseModel):
    approve: bool
    notes: str = ""


@router.get("")
def list_approvals(status_filter: str | None = None, db: Session = Depends(get_db), user=Depends(get_current_user)):
    q = db.query(Approval)
    if status_filter:
        q = q.filter(Approval.status == status_filter)
    approvals = q.order_by(Approval.id.desc()).limit(200).all()
    return [
        {
            "id": a.id, "action_type": a.action_type, "summary": a.summary, "payload": a.payload,
            "estimated_cost_usd": a.estimated_cost_usd, "risk_level": a.risk_level, "status": a.status,
            "requested_by_agent": a.requested_by_agent, "requested_at": a.requested_at,
            "decided_at": a.decided_at, "decided_by": a.decided_by,
        }
        for a in approvals
    ]


@router.post("/{approval_id}/decide")
def decide(approval_id: int, body: DecisionRequest, db: Session = Depends(get_db), user=Depends(get_current_user)):
    try:
        approval = decide_approval(db, approval_id, approve=body.approve, decided_by=user.email, notes=body.notes)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    run = resume_after_approval(db, approval_id)
    return {
        "approval_id": approval.id, "status": approval.status,
        "workflow_run_id": run.id if run else None,
        "workflow_status": run.status if run else None,
    }
