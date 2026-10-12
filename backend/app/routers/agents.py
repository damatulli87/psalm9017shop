from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.security import get_current_user
from app.database import get_db
from app.models.models import Agent, AIUsageRecord

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("")
def list_agents(db: Session = Depends(get_db), user=Depends(get_current_user)):
    agents = db.query(Agent).order_by(Agent.id).all()
    out = []
    for a in agents:
        usage = db.query(AIUsageRecord).filter(AIUsageRecord.agent_key == a.key).all()
        total_cost = sum(u.cost_usd for u in usage)
        call_count = len(usage)
        out.append({
            "key": a.key, "name": a.name, "responsibility": a.responsibility, "status": a.status,
            "current_task": a.current_task, "tools": a.tools, "total_cost_usd": round(total_cost, 4),
            "ai_call_count": call_count,
        })
    return out


@router.get("/{agent_key}")
def get_agent(agent_key: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    a = db.query(Agent).filter(Agent.key == agent_key).first()
    if not a:
        return {"error": "not found"}
    return {
        "key": a.key, "name": a.name, "responsibility": a.responsibility, "system_prompt": a.system_prompt,
        "status": a.status, "current_task": a.current_task, "tools": a.tools, "permissions": a.permissions,
    }
