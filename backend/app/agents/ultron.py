"""
ULTRON -- Chief Executive AI (spec section 4): "monitoring execution",
"identifying operational problems", "evaluating new opportunities".

This is a real, independent verifier, not a report generator that trusts
other agents' self-reported status. Every check here re-derives a
conclusion from the raw rows (QAResult, Task, Expense, Agent.status, files
on disk) and compares it against what the responsible agent/stage claimed.
Like the policy engine, there is no LLM call in this file -- ULTRON's job
is to catch real inconsistencies with measurable signals, not to form an
opinion. A "blocked" verdict always comes with the specific check that
failed and the data that proves it.

Two kinds of review:
  - review_workflow_run(): checked at defined checkpoints inside a single
    pipeline run (see workflow_engine.py) and again at the end, covering
    everything that run touched.
  - system_health_check(): a system-wide sweep (scheduled daily) that isn't
    tied to any one run -- agent error states, stale approvals, stuck
    workflows, budget pressure.

A "blocked" verdict opens a real Approval row (action_type=
"operational_concern") so it surfaces in the owner's Approval Center --
ULTRON cannot resolve its own concerns; it can only raise them.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.agents.base import BaseAgent
from app.config import settings
from app.models.models import (
    Agent,
    Approval,
    Expense,
    MarketOpportunity,
    MarketplaceListing,
    OperatingPolicy,
    OpportunityScore,
    ProductAsset,
    ProductSpecification,
    QAResult,
    SupervisionReview,
    Task,
    WorkflowRun,
)

PASS, WARN, FAIL = "pass", "warn", "fail"
EPSILON = 0.01


def _finding(check: str, status: str, detail: str) -> dict:
    return {"check": check, "status": status, "detail": detail}


def _verdict_from(findings: list[dict]) -> str:
    if any(f["status"] == FAIL for f in findings):
        return "blocked"
    if any(f["status"] == WARN for f in findings):
        return "warning"
    return "pass"


class UltronSupervisorAgent(BaseAgent):
    key = "ultron"

    # ------------------------------------------------------------ checks --
    def verify_opportunity_selection(self, opportunity: MarketOpportunity, score: OpportunityScore) -> list[dict]:
        findings = []

        weights = score.weights or {}
        recomputed = (
            score.demand_score * weights.get("demand_evidence", 0)
            + score.competition_score * weights.get("competitive_opportunity", 0)
            + score.profitability_score * weights.get("estimated_profitability", 0)
            + score.feasibility_score * weights.get("production_feasibility", 0)
            + score.differentiation_score * weights.get("differentiation_potential", 0)
            + score.risk_score * weights.get("risk", 0)
        )
        if abs(recomputed - score.weighted_total) > EPSILON:
            findings.append(_finding(
                "score_recomputation", FAIL,
                f"Recomputed weighted total {recomputed:.3f} does not match stored score "
                f"{score.weighted_total:.3f} for opportunity #{opportunity.id} -- scoring logic may be inconsistent.",
            ))
        else:
            findings.append(_finding("score_recomputation", PASS, f"Weighted total {score.weighted_total:.3f} verified independently."))

        min_row = self.db.query(OperatingPolicy).filter(OperatingPolicy.key == "minimum_opportunity_score").first()
        minimum = min_row.value if min_row and isinstance(min_row.value, (int, float)) else 0.55
        if score.decision == "selected" and score.weighted_total < minimum:
            findings.append(_finding(
                "decision_consistency", FAIL,
                f"Opportunity #{opportunity.id} marked 'selected' with score {score.weighted_total:.3f} "
                f"below the configured minimum {minimum:.3f}.",
            ))
        else:
            findings.append(_finding("decision_consistency", PASS, "Decision is consistent with the configured minimum score."))

        if not opportunity.evidence_summary.get("is_real_data"):
            findings.append(_finding(
                "evidence_quality", WARN,
                f"Opportunity #{opportunity.id} was selected without verified real-world demand data "
                f"(confidence: {score.confidence_level}). Proceeding on low-confidence evidence.",
            ))
        else:
            findings.append(_finding("evidence_quality", PASS, "Selection backed by verified real demand data."))

        return findings

    def verify_qa(self, product: ProductSpecification) -> list[dict]:
        findings = []
        qa_rows = self.db.query(QAResult).filter(QAResult.product_id == product.id).all()
        all_passed = bool(qa_rows) and all(r.passed for r in qa_rows)

        if product.status == "qa_passed" and not all_passed:
            findings.append(_finding(
                "qa_status_consistency", FAIL,
                f"Product #{product.id} is marked qa_passed but independently recomputing QAResult rows "
                f"gives {'no checks recorded' if not qa_rows else 'at least one failed check'}.",
            ))
        elif product.status == "qa_failed" and all_passed and qa_rows:
            findings.append(_finding(
                "qa_status_consistency", FAIL,
                f"Product #{product.id} is marked qa_failed but every recorded QAResult actually passed.",
            ))
        else:
            findings.append(_finding("qa_status_consistency", PASS, f"product.status matches independently recomputed QA result ({len(qa_rows)} checks)."))

        expected_checks = {"main_file_exists", "preview_image_valid", "zip_package_valid"}
        present_checks = {r.check_name for r in qa_rows}
        missing = expected_checks - present_checks
        if missing:
            findings.append(_finding("qa_completeness", WARN, f"Product #{product.id} is missing mandatory QA checks: {sorted(missing)}."))
        else:
            findings.append(_finding("qa_completeness", PASS, "All mandatory QA checks are present."))

        assets = self.db.query(ProductAsset).filter(ProductAsset.product_id == product.id).all()
        missing_files = [a.file_path for a in assets if not Path(a.file_path).exists()]
        if missing_files:
            findings.append(_finding("assets_present_on_disk", FAIL, f"Product #{product.id} has {len(missing_files)} registered asset(s) missing from disk: {missing_files}."))
        else:
            findings.append(_finding("assets_present_on_disk", PASS, f"All {len(assets)} registered asset(s) verified present on disk."))

        return findings

    def verify_publish_authorization(self, product: ProductSpecification) -> list[dict]:
        findings = []
        listing = self.db.query(MarketplaceListing).filter(MarketplaceListing.product_id == product.id).first()
        if not listing:
            return findings

        gated_states = {"pending_approval", "approved", "published", "published_simulated"}
        if listing.status in gated_states:
            approval = (
                self.db.query(Approval)
                .filter(Approval.action_type == "publish_listing")
                .order_by(Approval.id.desc())
                .all()
            )
            matching = [a for a in approval if a.payload.get("listing_id") == listing.id]
            if not matching:
                findings.append(_finding(
                    "publish_requires_approval_record", FAIL,
                    f"Listing #{listing.id} is in state '{listing.status}' but no Approval row references it -- "
                    "the policy engine may have been bypassed.",
                ))
            elif listing.status in {"published", "published_simulated"} and not any(a.status == "approved" for a in matching):
                findings.append(_finding(
                    "publish_requires_owner_approval", FAIL,
                    f"Listing #{listing.id} is '{listing.status}' but its linked Approval was never marked approved.",
                ))
            else:
                findings.append(_finding("publish_authorization", PASS, f"Listing #{listing.id} publish path has a valid, owner-approved Approval record."))
        return findings

    def verify_tasks(self, run: WorkflowRun) -> list[dict]:
        findings = []
        tasks = self.db.query(Task).filter(Task.workflow_run_id == run.id).all()
        failed = [t for t in tasks if t.status == "failed"]
        maxed_retries = [t for t in tasks if t.retries >= settings.max_retries_per_task]
        if failed:
            findings.append(_finding("no_failed_tasks", FAIL, f"Run #{run.id} has {len(failed)} failed task(s): {[t.stage for t in failed]}."))
        else:
            findings.append(_finding("no_failed_tasks", PASS, "No failed tasks in this run."))
        if maxed_retries:
            findings.append(_finding("retry_budget", WARN, f"Run #{run.id} has task(s) that hit the retry ceiling: {[t.stage for t in maxed_retries]}."))
        return findings

    def verify_cost(self, run: WorkflowRun) -> list[dict]:
        findings = []
        total = sum(e.amount_usd for e in self.db.query(Expense).filter(Expense.workflow_run_id == run.id).all())
        cap = settings.max_spend_per_workflow_usd
        if total > cap:
            findings.append(_finding("workflow_cost_cap", FAIL, f"Run #{run.id} spent ${total:.2f}, exceeding the ${cap:.2f} per-workflow cap."))
        elif cap > 0 and total > cap * 0.8:
            findings.append(_finding("workflow_cost_cap", WARN, f"Run #{run.id} spent ${total:.2f}, within 80% of the ${cap:.2f} per-workflow cap."))
        else:
            findings.append(_finding("workflow_cost_cap", PASS, f"Run #{run.id} cost ${total:.2f}, well within the ${cap:.2f} cap."))
        return findings

    def verify_agent_health(self, run: WorkflowRun) -> list[dict]:
        findings = []
        agent_keys = {t.agent_key for t in self.db.query(Task).filter(Task.workflow_run_id == run.id).all()}
        errored = [k for k in agent_keys if (a := self.db.query(Agent).filter(Agent.key == k).first()) and a.status == "error"]
        if errored:
            findings.append(_finding("agent_health", FAIL, f"Agent(s) involved in run #{run.id} are in an error state: {errored}."))
        else:
            findings.append(_finding("agent_health", PASS, "All agents involved in this run are healthy."))
        return findings

    # -------------------------------------------------------- aggregators --
    def review_workflow_run(self, workflow_run_id: int) -> SupervisionReview:
        run = self.db.query(WorkflowRun).filter(WorkflowRun.id == workflow_run_id).first()
        if run is None:
            raise ValueError(f"WorkflowRun {workflow_run_id} not found")

        findings: list[dict] = []
        findings += self.verify_tasks(run)
        findings += self.verify_cost(run)
        findings += self.verify_agent_health(run)

        product_task = self.db.query(Task).filter(Task.workflow_run_id == run.id, Task.stage == "product_planning", Task.status == "completed").first()
        opp_task = self.db.query(Task).filter(Task.workflow_run_id == run.id, Task.stage == "opportunity_selection", Task.status == "completed").first()

        if opp_task and opp_task.output_data.get("selected_opportunity_id"):
            opp = self.db.query(MarketOpportunity).filter(MarketOpportunity.id == opp_task.output_data["selected_opportunity_id"]).first()
            score = self.db.query(OpportunityScore).filter(OpportunityScore.opportunity_id == opp.id).order_by(OpportunityScore.id.desc()).first() if opp else None
            if opp and score:
                findings += self.verify_opportunity_selection(opp, score)

        if product_task and product_task.output_data.get("product_id"):
            product = self.db.query(ProductSpecification).filter(ProductSpecification.id == product_task.output_data["product_id"]).first()
            if product:
                findings += self.verify_qa(product)
                findings += self.verify_publish_authorization(product)

        verdict = _verdict_from(findings)
        fail_count = sum(1 for f in findings if f["status"] == FAIL)
        warn_count = sum(1 for f in findings if f["status"] == WARN)
        summary = (
            f"Run #{run.id} ({run.workflow_type}): {len(findings)} checks -- "
            f"{fail_count} failed, {warn_count} warned, {len(findings) - fail_count - warn_count} passed."
        )

        review = SupervisionReview(scope="workflow_run", scope_id=str(run.id), verdict=verdict, summary=summary, findings=findings)
        self.db.add(review)
        self.db.commit()
        self.db.refresh(review)

        self.log(
            "supervision_review" if verdict == "pass" else f"supervision_{verdict}",
            summary,
            {"review_id": review.id, "workflow_run_id": run.id, "verdict": verdict},
        )

        if verdict == "blocked":
            self._raise_concern(
                summary=f"ULTRON oversight BLOCKED on workflow run #{run.id}: {summary}",
                payload={"review_id": review.id, "workflow_run_id": run.id, "findings": findings},
            )

        return review

    def system_health_check(self) -> SupervisionReview:
        findings: list[dict] = []

        errored_agents = self.db.query(Agent).filter(Agent.status == "error").all()
        if errored_agents:
            findings.append(_finding("agent_fleet_health", FAIL, f"{len(errored_agents)} agent(s) in error state: {[a.key for a in errored_agents]}."))
        else:
            findings.append(_finding("agent_fleet_health", PASS, "No agents are in an error state."))

        month_start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        month_spend = sum(e.amount_usd for e in self.db.query(Expense).filter(Expense.incurred_at >= month_start).all())
        if month_spend > settings.startup_budget_ceiling_usd:
            findings.append(_finding("startup_budget", FAIL, f"Month-to-date spend ${month_spend:.2f} exceeds the startup ceiling ${settings.startup_budget_ceiling_usd:.2f}."))
        elif month_spend > settings.startup_budget_ceiling_usd * 0.8:
            findings.append(_finding("startup_budget", WARN, f"Month-to-date spend ${month_spend:.2f} is within 80% of the startup ceiling."))
        else:
            findings.append(_finding("startup_budget", PASS, f"Month-to-date spend ${month_spend:.2f} is well within budget."))

        stale_cutoff = datetime.now(timezone.utc) - timedelta(minutes=30)
        stuck_runs = self.db.query(WorkflowRun).filter(WorkflowRun.status == "running", WorkflowRun.started_at < stale_cutoff).all()
        if stuck_runs:
            findings.append(_finding("stuck_workflows", WARN, f"{len(stuck_runs)} workflow run(s) have been 'running' for over 30 minutes: {[r.id for r in stuck_runs]} -- possible crash."))
        else:
            findings.append(_finding("stuck_workflows", PASS, "No workflow runs appear stuck."))

        approval_cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        stale_approvals = self.db.query(Approval).filter(Approval.status == "pending", Approval.requested_at < approval_cutoff).all()
        if stale_approvals:
            findings.append(_finding("stale_approvals", WARN, f"{len(stale_approvals)} approval(s) have been pending for over 7 days: {[a.id for a in stale_approvals]}."))
        else:
            findings.append(_finding("stale_approvals", PASS, "No approvals are stale."))

        verdict = _verdict_from(findings)
        fail_count = sum(1 for f in findings if f["status"] == FAIL)
        warn_count = sum(1 for f in findings if f["status"] == WARN)
        summary = f"System health check: {len(findings)} checks -- {fail_count} failed, {warn_count} warned, {len(findings) - fail_count - warn_count} passed."

        review = SupervisionReview(scope="system", scope_id="global", verdict=verdict, summary=summary, findings=findings)
        self.db.add(review)
        self.db.commit()
        self.db.refresh(review)

        self.log(
            "supervision_review" if verdict == "pass" else f"supervision_{verdict}",
            summary,
            {"review_id": review.id, "verdict": verdict},
        )

        if verdict == "blocked":
            self._raise_concern(
                summary=f"ULTRON system health check BLOCKED: {summary}",
                payload={"review_id": review.id, "findings": findings},
            )

        return review

    def _raise_concern(self, *, summary: str, payload: dict) -> None:
        self.db.add(Approval(
            action_type="operational_concern",
            summary=summary,
            payload=payload,
            estimated_cost_usd=0.0,
            risk_level="high",
            requested_by_agent=self.key,
            status="pending",
        ))
        self.db.commit()
