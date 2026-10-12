"""
Financial Controller Agent (spec section 17).

Reads real DB rows only -- Transactions (sales/refunds/fees) and Expenses
(AI/hosting/subscriptions/ads/production). Every figure is tagged with its
basis so the report can never silently blend ACTUAL revenue with PROJECTED
revenue. Until a real storefront is connected, gross/net revenue is
genuinely $0.00 ACTUAL -- this agent will not invent sales to look busy.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.agents.base import BaseAgent
from app.models.models import Expense, Transaction


class FinancialControllerAgent(BaseAgent):
    key = "financial_controller"

    def generate_report(self) -> dict:
        transactions = self.db.query(Transaction).all()
        expenses = self.db.query(Expense).all()

        actual_sales = sum(t.amount_usd for t in transactions if t.type == "sale" and t.basis == "ACTUAL")
        actual_refunds = sum(t.amount_usd for t in transactions if t.type == "refund" and t.basis == "ACTUAL")
        actual_expenses = sum(e.amount_usd for e in expenses if e.basis == "ACTUAL")
        projected_sales = sum(t.amount_usd for t in transactions if t.basis in ("ESTIMATED", "PROJECTED"))

        net_revenue_actual = round(actual_sales - actual_refunds, 2)
        operating_profit_actual = round(net_revenue_actual - actual_expenses, 2)

        expense_by_category: dict[str, float] = {}
        for e in expenses:
            expense_by_category[e.category] = round(expense_by_category.get(e.category, 0.0) + e.amount_usd, 2)

        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "ACTUAL": {
                "gross_sales_usd": round(actual_sales, 2),
                "refunds_usd": round(actual_refunds, 2),
                "net_revenue_usd": net_revenue_actual,
                "total_expenses_usd": round(actual_expenses, 2),
                "operating_profit_usd": operating_profit_actual,
                "expenses_by_category": expense_by_category,
            },
            "PROJECTED": {
                "projected_sales_usd": round(projected_sales, 2),
                "note": "Projected figures are estimates and are NEVER included in ACTUAL totals above.",
            },
            "UNKNOWN": {
                "note": "No connected marketplace means real order/sales data cannot yet be retrieved. "
                         "See /integrations status for which channels are verified vs awaiting configuration.",
            },
        }
        self.log("financial_report_generated", "Financial report generated from real ledger rows.", report)
        return report
