"""Thin helper for recording real expenses with an explicit ACTUAL/ESTIMATED basis."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.models import Expense


def record_expense(
    db: Session,
    *,
    category: str,
    amount_usd: float,
    basis: str = "ACTUAL",
    description: str = "",
    workflow_run_id: int | None = None,
    agent_key: str | None = None,
) -> Expense:
    expense = Expense(
        category=category,
        amount_usd=amount_usd,
        basis=basis,
        description=description,
        workflow_run_id=workflow_run_id,
        agent_key=agent_key,
    )
    db.add(expense)
    db.commit()
    db.refresh(expense)
    return expense
