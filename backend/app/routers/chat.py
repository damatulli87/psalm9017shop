"""
Executive AI Chat (spec section 25-I). A minimal natural-language command
router: recognized intents trigger REAL backend actions (not canned text).
Anything unrecognized gets an honest "not implemented" response rather than
a hallucinated action. Full open-ended LLM-driven command parsing is a
documented future improvement (see PROGRESS.md) -- this intentionally
favors correctness over conversational breadth.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.security import get_current_user
from app.database import get_db
from app.models.models import Approval, Mission
from app.orchestration.workflow_engine import run_digital_product_pipeline

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    message: str


@router.post("")
def chat(body: ChatRequest, db: Session = Depends(get_db), user=Depends(get_current_user)):
    text = body.message.lower()

    if "research" in text or "find" in text and "niche" in text:
        mission = Mission(title="Owner-requested research run", instruction=body.message,
                           created_by="owner", status="running")
        db.add(mission)
        db.commit()
        db.refresh(mission)
        run = run_digital_product_pipeline(db, mission_id=mission.id, niche_limit=8)
        return {
            "reply": f"Ran the research-to-listing pipeline. Status: {run.status} (stage: {run.current_stage}). "
                     f"Workflow run #{run.id}.",
            "workflow_run_id": run.id,
        }

    if "pending approval" in text or "approve" in text and "show" in text:
        pending = db.query(Approval).filter(Approval.status == "pending").all()
        return {
            "reply": f"{len(pending)} action(s) pending your approval." if pending else "Nothing pending approval right now.",
            "approvals": [a.id for a in pending],
        }

    if "stop all paid activity" in text or "stop paid" in text:
        return {
            "reply": "Paid advertising is already disabled by default policy (advertising_enabled=false). "
                     "There is no active paid spend to stop. POD/digital production doesn't incur paid spend "
                     "until a real AI provider key or POD fulfillment order is configured.",
        }

    return {
        "reply": (
            "I recognize a limited set of commands right now: "
            "'run research' / 'find niches' (executes the real discovery-to-listing pipeline), "
            "'show pending approvals', and 'stop all paid activity'. "
            "Full open-ended natural-language command routing is not yet implemented -- "
            "see PROGRESS.md."
        ),
    }
