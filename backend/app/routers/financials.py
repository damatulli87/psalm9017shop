from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.agents.financial_controller import FinancialControllerAgent
from app.auth.security import get_current_user
from app.database import get_db
from app.policy.engine import month_to_date_total_spend

router = APIRouter(prefix="/financials", tags=["financials"])


@router.get("/report")
def report(db: Session = Depends(get_db), user=Depends(get_current_user)):
    agent = FinancialControllerAgent(db)
    data = agent.generate_report()
    data["month_to_date_total_spend_usd"] = round(month_to_date_total_spend(db), 2)
    return data
