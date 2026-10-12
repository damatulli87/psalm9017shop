from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.security import get_current_user
from app.config import settings
from app.database import get_db
from app.models.models import (
    Agent, Approval, Expense, MarketplaceListing, ProductSpecification, Storefront, Transaction, WorkflowRun,
)
from app.policy.engine import get_autonomy_mode, month_to_date_total_spend

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary")
def summary(db: Session = Depends(get_db), user=Depends(get_current_user)):
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    today_sales = sum(
        t.amount_usd for t in db.query(Transaction).filter(
            Transaction.type == "sale", Transaction.basis == "ACTUAL", Transaction.occurred_at >= today_start
        ).all()
    )
    month_sales = sum(
        t.amount_usd for t in db.query(Transaction).filter(
            Transaction.type == "sale", Transaction.basis == "ACTUAL", Transaction.occurred_at >= month_start
        ).all()
    )
    month_expenses = sum(
        e.amount_usd for e in db.query(Expense).filter(Expense.basis == "ACTUAL", Expense.incurred_at >= month_start).all()
    )

    agents = db.query(Agent).all()
    active_agents = [a.key for a in agents if a.status == "working"]

    products_in_dev = db.query(ProductSpecification).filter(
        ProductSpecification.status.in_(["planned", "produced"])
    ).count()
    published_listings = db.query(MarketplaceListing).filter(
        MarketplaceListing.status.in_(["published", "published_simulated"])
    ).count()
    pending_approvals = db.query(Approval).filter(Approval.status == "pending").count()

    recent_runs = db.query(WorkflowRun).order_by(WorkflowRun.id.desc()).limit(5).all()

    storefronts = db.query(Storefront).all()

    return {
        "today_sales_actual_usd": round(today_sales, 2),
        "month_sales_actual_usd": round(month_sales, 2),
        "month_operating_profit_actual_usd": round(month_sales - month_expenses, 2),
        "month_expenses_actual_usd": round(month_expenses, 2),
        "startup_budget_ceiling_usd": settings.startup_budget_ceiling_usd,
        "month_to_date_spend_usd": round(month_to_date_total_spend(db), 2),
        "autonomy_mode": get_autonomy_mode(db),
        "active_agent_count": len(active_agents),
        "active_agents": active_agents,
        "total_agent_count": len(agents),
        "products_in_development": products_in_dev,
        "published_listings": published_listings,
        "pending_approvals": pending_approvals,
        "recent_workflow_runs": [
            {"id": r.id, "type": r.workflow_type, "status": r.status, "stage": r.current_stage}
            for r in recent_runs
        ],
        "storefront_connections": [
            {"channel": s.channel, "connected": s.connected, "status": s.status_detail} for s in storefronts
        ],
        "system_health": "operational",
    }
