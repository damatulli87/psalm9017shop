"""
Base class every specialist agent inherits from (spec section 3).

Gives every agent: identity (loaded from the Agent DB row), structured
run() input/output, execution logging to AuditEvent, status tracking on
the Agent row, retry handling, and a hook for requesting owner approval
via the policy engine (agents cannot grant themselves permission).
"""
from __future__ import annotations

import traceback
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.models import Agent, AuditEvent
from app.policy import engine as policy_engine


class AgentError(Exception):
    pass


class BaseAgent:
    key: str = "base"

    def __init__(self, db: Session):
        self.db = db
        self.record = db.query(Agent).filter(Agent.key == self.key).first()
        if self.record is None:
            raise AgentError(f"Agent '{self.key}' not found -- did bootstrap() run?")

    # ---- status/logging -------------------------------------------------
    def _set_status(self, status: str, current_task: str | None = None) -> None:
        self.record.status = status
        self.record.current_task = current_task
        self.db.commit()

    def log(self, event_type: str, summary: str, payload: dict | None = None) -> None:
        self.db.add(AuditEvent(event_type=event_type, actor=self.key, summary=summary, payload=payload or {}))
        self.db.commit()

    def request_approval(
        self,
        *,
        action_type: str,
        summary: str,
        payload: dict | None = None,
        estimated_cost_usd: float = 0.0,
        risk_level: str = "low",
    ) -> policy_engine.AuthorizationResult:
        return policy_engine.authorize(
            self.db,
            action_type=action_type,
            requested_by_agent=self.key,
            summary=summary,
            payload=payload,
            estimated_cost_usd=estimated_cost_usd,
            risk_level=risk_level,
        )

    # ---- execution wrapper with retry + error capture --------------------
    def run_with_retries(self, task_name: str, fn, *args, max_retries: int = 3, **kwargs) -> Any:
        self._set_status("working", task_name)
        attempt = 0
        last_error: Exception | None = None
        while attempt <= max_retries:
            try:
                result = fn(*args, **kwargs)
                self._set_status("idle", None)
                self.log("task_completed", f"{task_name} succeeded on attempt {attempt + 1}")
                return result
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                attempt += 1
                self.log(
                    "task_retry" if attempt <= max_retries else "task_failed",
                    f"{task_name} failed on attempt {attempt}: {exc}",
                    {"traceback": traceback.format_exc()},
                )
        self._set_status("error", task_name)
        raise AgentError(f"{self.key}.{task_name} failed after {max_retries + 1} attempts: {last_error}") from last_error
