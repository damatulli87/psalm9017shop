"""
Policy & Approval Engine (spec section 22).

This module is intentionally NOT an AI agent. It is plain deterministic
Python that every agent action must pass through before anything
external-facing, money-spending, or destructive happens. Agents call
`policy.authorize(...)`; they cannot grant themselves permission, and
nothing in this file calls an LLM.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.config import settings
from app.models.models import Approval, AuditEvent, Expense, OperatingPolicy

# Actions that ALWAYS require explicit owner approval, regardless of
# autonomy mode. This list is enforced here, not inside any prompt.
ALWAYS_REQUIRES_APPROVAL = {
    "publish_listing",
    "new_paid_subscription",
    "advertising_spend",
    "purchase",
    "financial_account_change",
    "unapproved_fulfillment_spend",
    "refund_above_limit",
    "external_communication_outside_policy",
    "production_code_deployment",
    "permission_change",
    "destructive_data_operation",
    "pod_paid_production_order",
}

# Actions allowed to auto-execute in HYBRID/AUTONOMOUS mode (never SUPERVISED).
ROUTINE_ACTIONS = {
    "run_research",
    "score_opportunity",
    "generate_product_spec",
    "generate_design_brief",
    "generate_digital_product_files",
    "run_qa_checks",
    "prepare_listing_draft",  # drafting is not publishing
}


@dataclass
class AuthorizationResult:
    allowed: bool
    approval_id: int | None
    reason: str


def _get_policy_value(db: Session, key: str, default):
    row = db.query(OperatingPolicy).filter(OperatingPolicy.key == key).first()
    return row.value if row else default


def get_autonomy_mode(db: Session) -> str:
    return _get_policy_value(db, "autonomy_mode", settings.autonomy_mode)


def _log_audit(db: Session, event_type: str, actor: str, summary: str, payload: dict | None = None) -> None:
    db.add(AuditEvent(event_type=event_type, actor=actor, summary=summary, payload=payload or {}))
    db.commit()


def month_to_date_ai_spend(db: Session) -> float:
    start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    rows = db.query(Expense).filter(Expense.category == "ai_api", Expense.incurred_at >= start).all()
    return sum(r.amount_usd for r in rows)


def month_to_date_total_spend(db: Session) -> float:
    start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    rows = db.query(Expense).filter(Expense.incurred_at >= start).all()
    return sum(r.amount_usd for r in rows)


def budget_check(db: Session, category: str, amount_usd: float) -> AuthorizationResult:
    """Hard budget enforcement (section 23). Independent of autonomy mode."""
    if category == "ai_api":
        spent = month_to_date_ai_spend(db)
        if spent + amount_usd > settings.monthly_ai_budget_usd:
            return AuthorizationResult(
                False, None,
                f"Monthly AI budget exceeded: ${spent:.2f} spent + ${amount_usd:.2f} requested > "
                f"${settings.monthly_ai_budget_usd:.2f} cap.",
            )
    if amount_usd > settings.max_spend_per_action_usd:
        return AuthorizationResult(
            False, None,
            f"Requested ${amount_usd:.2f} exceeds max-per-action cap of ${settings.max_spend_per_action_usd:.2f}.",
        )
    total_spent = month_to_date_total_spend(db)
    if total_spent + amount_usd > settings.startup_budget_ceiling_usd:
        return AuthorizationResult(
            False, None,
            f"Would exceed startup budget ceiling of ${settings.startup_budget_ceiling_usd:.2f}.",
        )
    return AuthorizationResult(True, None, "within budget")


def authorize(
    db: Session,
    *,
    action_type: str,
    requested_by_agent: str,
    summary: str,
    payload: dict | None = None,
    estimated_cost_usd: float = 0.0,
    risk_level: str = "low",
) -> AuthorizationResult:
    """
    The single choke point every agent must call before doing anything
    external-facing or costly. Returns allowed=True only if the action may
    proceed immediately; otherwise an Approval row is created and the
    workflow must pause (see orchestration/workflow_engine.py).
    """
    payload = payload or {}

    if action_type == "advertising_spend" and not settings.advertising_enabled:
        reason = "Advertising is disabled by policy until the owner explicitly enables it."
        _log_audit(db, "policy_block", requested_by_agent, reason, payload)
        return AuthorizationResult(False, None, reason)

    if estimated_cost_usd > 0:
        budget_result = budget_check(db, payload.get("budget_category", "other"), estimated_cost_usd)
        if not budget_result.allowed:
            _log_audit(db, "budget_block", requested_by_agent, budget_result.reason, payload)
            return budget_result

    mode = get_autonomy_mode(db)
    needs_approval = action_type in ALWAYS_REQUIRES_APPROVAL
    if mode == "SUPERVISED" and action_type not in ROUTINE_ACTIONS:
        needs_approval = True

    if not needs_approval:
        _log_audit(db, "action_autoexecuted", requested_by_agent, summary, payload)
        return AuthorizationResult(True, None, f"Auto-authorized under {mode} mode.")

    approval = Approval(
        action_type=action_type,
        summary=summary,
        payload=payload,
        estimated_cost_usd=estimated_cost_usd,
        risk_level=risk_level,
        requested_by_agent=requested_by_agent,
        status="pending",
    )
    db.add(approval)
    db.commit()
    db.refresh(approval)
    _log_audit(db, "approval_requested", requested_by_agent, summary, {"approval_id": approval.id, **payload})
    return AuthorizationResult(False, approval.id, "Queued for owner approval.")


def decide_approval(db: Session, approval_id: int, *, approve: bool, decided_by: str, notes: str = "") -> Approval:
    approval = db.query(Approval).filter(Approval.id == approval_id).first()
    if not approval:
        raise ValueError(f"Approval {approval_id} not found")
    approval.status = "approved" if approve else "rejected"
    approval.decided_at = datetime.now(timezone.utc)
    approval.decided_by = decided_by
    approval.notes = notes
    db.commit()
    _log_audit(
        db, "approval_decided", decided_by,
        f"Approval #{approval_id} ({approval.action_type}) -> {approval.status}",
        {"approval_id": approval_id, "notes": notes},
    )
    return approval
