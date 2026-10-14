"""Thin helpers for recording real money with an explicit ACTUAL/ESTIMATED basis."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.models import Expense, Transaction


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


def record_transaction(
    db: Session,
    *,
    type: str,
    amount_usd: float,
    basis: str = "ACTUAL",
    description: str = "",
    order_id: int | None = None,
) -> Transaction:
    """type: sale/refund/fee/expense -- real revenue (a sale) flows through
    here, not record_expense(), which is cost-only."""
    txn = Transaction(
        order_id=order_id, type=type, amount_usd=amount_usd, basis=basis, description=description,
    )
    db.add(txn)
    db.commit()
    db.refresh(txn)
    return txn
