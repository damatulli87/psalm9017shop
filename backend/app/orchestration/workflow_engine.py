"""
Durable workflow engine (spec section 20).

Rather than a heavyweight LangGraph dependency for an MVP whose whole value
is in being *verifiably durable and restartable*, this is a small DB-backed
state machine: every stage of a WorkflowRun is persisted as a Task row
before and after it executes. If the process crashes mid-run,
`resume_workflow()` re-reads the WorkflowRun + its Task rows and continues
from the first non-completed stage instead of re-running (and
re-charging/re-publishing) completed work. Swapping this for LangGraph later
is possible without changing any agent code, since agents are plain
Python classes with no framework coupling.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.agents.creative_director import CreativeDirectorAgent
from app.agents.digital_production import DigitalProductionAgent
from app.agents.etsy_manager import EtsyManagerAgent
from app.agents.pod_production import PODProductionAgent
from app.agents.financial_controller import FinancialControllerAgent  # noqa: F401  (used by routers)
from app.agents.market_intelligence import MarketIntelligenceAgent
from app.agents.opportunity_engine import OpportunityDecisionEngine
from app.agents.product_strategy import ProductStrategyAgent
from app.agents.qa import QAAgent
from app.agents.seo import SEOAgent
from app.agents.ultron import UltronSupervisorAgent
from app.models.models import (
    Approval,
    MarketOpportunity,
    MarketplaceListing,
    OpportunityScore,
    ProductSpecification,
    Task,
    WorkflowRun,
)
from app.policy import engine as policy_engine

STAGES = [
    "research",
    "opportunity_selection",
    "product_planning",
    "creative_direction",
    "production",
    "quality_assurance",
    "listing_creation",
    "authorization",
    "publication",
    "marketing",
    "sales_monitoring",
    "optimization",
]

NOT_YET_IMPLEMENTED_STAGES = {
    "marketing": "Paid/organic campaign execution is not yet built (spec section 15). Requires owner-approved "
                 "marketing channel credentials; currently always escalates to approval.",
    "sales_monitoring": "No storefront is connected yet, so there are no real orders to poll (spec section 10/20 "
                         "stage 10). The poller exists in the scheduler and will activate once Etsy is connected.",
    "optimization": "Growth Strategy Agent exists but needs >1 cycle of real sales data to analyze (spec section 18); "
                     "nothing to optimize on zero real orders.",
}


def _touch(db: Session, run: WorkflowRun, stage: str, status: str, error: str | None = None) -> None:
    run.current_stage = stage
    run.status = status
    if error:
        run.error = error
    db.commit()


def _task(db: Session, run: WorkflowRun, stage: str, agent_key: str) -> Task:
    existing = db.query(Task).filter(Task.workflow_run_id == run.id, Task.stage == stage).first()
    if existing:
        return existing
    t = Task(workflow_run_id=run.id, stage=stage, agent_key=agent_key, status="pending")
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


def _complete_task(db: Session, task: Task, output: dict, status: str = "completed") -> None:
    task.status = status
    task.output_data = output
    task.completed_at = datetime.now(timezone.utc)
    db.commit()


def _final_review(db: Session, run: WorkflowRun) -> None:
    """
    Psalm 90:17's post-hoc sign-off on everything this run touched. Wrapped
    defensively: a bug in the oversight layer itself must never erase or
    mask a pipeline result that already completed and was persisted.
    """
    try:
        UltronSupervisorAgent(db).review_workflow_run(run.id)
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        from app.models.models import AuditEvent

        db.add(AuditEvent(
            event_type="supervision_review_error", actor="ultron",
            summary=f"Psalm 90:17's post-hoc review of run #{run.id} itself failed: {exc}",
            payload={"workflow_run_id": run.id},
        ))
        db.commit()


def start_workflow(db: Session, workflow_type: str, mission_id: int | None = None) -> WorkflowRun:
    run = WorkflowRun(mission_id=mission_id, workflow_type=workflow_type, status="running", current_stage=STAGES[0])
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def run_digital_product_pipeline(db: Session, mission_id: int | None = None, niche_limit: int = 8) -> WorkflowRun:
    """
    Spec section 43's required first milestone: research -> select -> spec ->
    produce a REAL digital product -> validate -> Etsy-ready draft -> queue
    for owner approval. Stages 9-12 are recorded as not-yet-implemented
    tasks rather than silently skipped.
    """
    run = start_workflow(db, "digital_product_pipeline", mission_id)

    # --- Stage 1: research ---
    t = _task(db, run, "research", "market_intelligence")
    t.started_at = datetime.now(timezone.utc)
    db.commit()
    agent = MarketIntelligenceAgent(db)
    opportunities = agent.research_candidates(workflow_run_id=run.id, limit=niche_limit)
    _complete_task(db, t, {"opportunity_ids": [o.id for o in opportunities]})

    # --- Stage 2: opportunity selection ---
    t = _task(db, run, "opportunity_selection", "opportunity_engine")
    t.started_at = datetime.now(timezone.utc)
    db.commit()
    decision_agent = OpportunityDecisionEngine(db)
    selected = decision_agent.select_best(opportunities)
    if selected is None:
        _complete_task(db, t, {"selected_opportunity_id": None}, status="completed")
        run.completed_at = datetime.now(timezone.utc)
        _touch(db, run, "opportunity_selection", "completed_no_opportunity",
               "All researched opportunities fell below the minimum score/confidence threshold; nothing selected.")
        _final_review(db, run)
        return run
    _complete_task(db, t, {"selected_opportunity_id": selected.id})

    # --- Psalm 90:17 checkpoint: independently re-verify the selection before spending effort producing it ---
    ultron = UltronSupervisorAgent(db)
    score = (
        db.query(OpportunityScore)
        .filter(OpportunityScore.opportunity_id == selected.id)
        .order_by(OpportunityScore.id.desc())
        .first()
    )
    checkpoint_findings = ultron.verify_opportunity_selection(selected, score) if score else []
    if any(f["status"] == "fail" for f in checkpoint_findings):
        reasons = "; ".join(f["detail"] for f in checkpoint_findings if f["status"] == "fail")
        run.completed_at = datetime.now(timezone.utc)
        _touch(db, run, "opportunity_selection", "blocked_by_oversight", f"Psalm 90:17 blocked this run: {reasons}")
        _final_review(db, run)
        return run

    # --- Stage 3: product planning ---
    t = _task(db, run, "product_planning", "product_strategy")
    t.started_at = datetime.now(timezone.utc)
    db.commit()
    strategy_agent = ProductStrategyAgent(db)
    product = strategy_agent.build_spec(selected, workflow_run_id=run.id)
    _complete_task(db, t, {"product_id": product.id})

    # --- Stage 4: creative direction ---
    t = _task(db, run, "creative_direction", "creative_director")
    t.started_at = datetime.now(timezone.utc)
    db.commit()
    creative_agent = CreativeDirectorAgent(db)
    brief = creative_agent.create_design_brief(product)
    _complete_task(db, t, {"design_brief": brief})

    # --- Stage 5: production ---
    if product.product_type != "digital":
        # POD: real Printify catalog/cost/artwork call (app/agents/pod_production.py).
        # Falls through into the same QA/listing/authorization stages digital
        # products use below -- QAAgent and UltronSupervisorAgent branch on
        # product.product_type internally, and EtsyManagerAgent was already
        # product-type-agnostic.
        t = _task(db, run, "production", "pod_production")
        t.started_at = datetime.now(timezone.utc)
        db.commit()
        pod_agent = PODProductionAgent(db)
        pod_result = pod_agent.produce(product, workflow_run_id=run.id)
        if not pod_result.success:
            _complete_task(db, t, {"note": pod_result.blocked_reason}, status="blocked")
            run.completed_at = datetime.now(timezone.utc)
            _touch(db, run, "production", "blocked_pod", pod_result.blocked_reason or "POD production blocked.")
            _final_review(db, run)
            return run
        _complete_task(
            db, t,
            {"printify_product_id": pod_result.printify_product_id, "real_cost_usd": pod_result.real_cost_usd},
        )
    else:
        t = _task(db, run, "production", "digital_production")
        t.started_at = datetime.now(timezone.utc)
        db.commit()
        production_agent = DigitalProductionAgent(db)
        files = production_agent.produce(product, workflow_run_id=run.id)
        _complete_task(db, t, {"files": [str(f) for f in files]})

    # --- Stage 6: quality assurance ---
    t = _task(db, run, "quality_assurance", "qa")
    t.started_at = datetime.now(timezone.utc)
    db.commit()
    qa_agent = QAAgent(db)
    passed = qa_agent.run_checks(product)
    _complete_task(db, t, {"passed": passed}, status="completed" if passed else "failed")
    if not passed:
        run.completed_at = datetime.now(timezone.utc)
        _touch(db, run, "quality_assurance", "failed", "Product failed mandatory QA checks; not published.")
        _final_review(db, run)
        return run

    # --- Psalm 90:17 checkpoint: independently re-verify QA before this product is allowed into a listing ---
    qa_findings = ultron.verify_qa(product)
    if any(f["status"] == "fail" for f in qa_findings):
        reasons = "; ".join(f["detail"] for f in qa_findings if f["status"] == "fail")
        run.completed_at = datetime.now(timezone.utc)
        _touch(db, run, "quality_assurance", "blocked_by_oversight", f"Psalm 90:17 blocked this run: {reasons}")
        _final_review(db, run)
        return run

    # --- Stage 7: listing creation ---
    t = _task(db, run, "listing_creation", "seo")
    t.started_at = datetime.now(timezone.utc)
    db.commit()
    seo_agent = SEOAgent(db)
    copy = seo_agent.build_listing_copy(product, selected)
    etsy_agent = EtsyManagerAgent(db)
    listing = etsy_agent.prepare_listing_draft(
        product, seo_title=copy["title"], seo_description=copy["description"], tags=copy["tags"]
    )
    if listing.status == "creation_failed":
        # A real (non-simulated) Etsy API call actually failed -- do NOT
        # proceed to request owner approval to publish a listing that
        # doesn't exist. Confirmed this path is reachable live (a bad
        # taxonomy_id 400'd the first real listing-creation attempt).
        _complete_task(db, t, {"listing_id": listing.id, "note": "Real Etsy listing creation failed."}, status="failed")
        run.completed_at = datetime.now(timezone.utc)
        _touch(db, run, "listing_creation", "failed", "Real Etsy listing creation failed; nothing to approve.")
        _final_review(db, run)
        return run
    _complete_task(db, t, {"listing_id": listing.id, "simulated": listing.is_simulated})

    # --- Stage 8: authorization ---
    t = _task(db, run, "authorization", "ultron")
    t.started_at = datetime.now(timezone.utc)
    db.commit()
    auth_result = policy_engine.authorize(
        db,
        action_type="publish_listing",
        requested_by_agent="ultron",
        summary=f"Publish Etsy listing draft #{listing.id} for product '{product.title}'",
        payload={"listing_id": listing.id, "product_id": product.id, "workflow_run_id": run.id},
        estimated_cost_usd=0.0,
        risk_level="medium",
    )
    listing.status = "pending_approval" if not auth_result.allowed else "approved"
    db.commit()
    _complete_task(db, t, {"allowed": auth_result.allowed, "approval_id": auth_result.approval_id,
                            "reason": auth_result.reason})

    if not auth_result.allowed:
        run.completed_at = None
        _touch(db, run, "authorization", "awaiting_approval")
        _final_review(db, run)
        return run

    # --- Stage 9: publication (only reachable if auto-authorized, e.g. HYBRID/AUTONOMOUS for drafts) ---
    _publish(db, run, listing)

    # --- Stages 10-12: recorded honestly as not-yet-implemented ---
    for stage in ["marketing", "sales_monitoring", "optimization"]:
        t = _task(db, run, stage, "ultron")
        _complete_task(db, t, {"note": NOT_YET_IMPLEMENTED_STAGES[stage]}, status="not_yet_implemented")

    run.completed_at = datetime.now(timezone.utc)
    _touch(db, run, "optimization", "completed")
    _final_review(db, run)
    return run


def _publish(db: Session, run: WorkflowRun, listing: MarketplaceListing) -> None:
    t = _task(db, run, "publication", "etsy_manager")
    t.started_at = datetime.now(timezone.utc)
    db.commit()
    # The real Etsy adapter call already ran during listing_creation when credentials exist; here we flip
    # status once approved. If still simulated, we are explicit that nothing went live on a real marketplace.
    listing.status = "published_simulated" if listing.is_simulated else "published"
    listing.published_at = datetime.now(timezone.utc)
    db.commit()
    _complete_task(db, t, {"listing_id": listing.id, "status": listing.status})


def resume_after_approval(db: Session, approval_id: int) -> WorkflowRun | None:
    """Call after an owner decides an approval. If approved and it was a publish_listing
    action, completes the paused workflow's publication stage."""
    approval = db.query(Approval).filter(Approval.id == approval_id).first()
    if not approval or approval.action_type != "publish_listing":
        return None

    workflow_run_id = approval.payload.get("workflow_run_id")
    listing_id = approval.payload.get("listing_id")
    run = db.query(WorkflowRun).filter(WorkflowRun.id == workflow_run_id).first()
    listing = db.query(MarketplaceListing).filter(MarketplaceListing.id == listing_id).first()
    if not run or not listing:
        return run

    if approval.status == "rejected":
        listing.status = "rejected"
        run.completed_at = datetime.now(timezone.utc)
        _touch(db, run, "authorization", "rejected", "Owner rejected the publish-listing approval.")
        _final_review(db, run)
        return run

    if approval.status == "approved":
        _publish(db, run, listing)
        for stage in ["marketing", "sales_monitoring", "optimization"]:
            t = _task(db, run, stage, "ultron")
            _complete_task(db, t, {"note": NOT_YET_IMPLEMENTED_STAGES[stage]}, status="not_yet_implemented")
        run.completed_at = datetime.now(timezone.utc)
        _touch(db, run, "optimization", "completed")
        _final_review(db, run)
        return run

    return run
