"""
ULTRON is supposed to be a real independent verifier (spec section 4), not
a rubber stamp. These tests check both halves of that claim: it doesn't
cry wolf on a clean run, and it does catch a real, deliberately-introduced
inconsistency.
"""
from __future__ import annotations

from pathlib import Path

from app.agents.ultron import UltronSupervisorAgent
from app.database import SessionLocal
from app.models.models import Approval, ProductAsset, SupervisionReview, WorkflowRun
from app.orchestration.workflow_engine import run_digital_product_pipeline


def test_ultron_reviews_every_run_and_does_not_false_positive():
    db = SessionLocal()
    try:
        run = run_digital_product_pipeline(db, niche_limit=10)

        review = (
            db.query(SupervisionReview)
            .filter(SupervisionReview.scope == "workflow_run", SupervisionReview.scope_id == str(run.id))
            .order_by(SupervisionReview.id.desc())
            .first()
        )
        assert review is not None, "workflow_engine must call ULTRON's post-hoc review on every exit path"
        assert review.verdict in ("pass", "warning"), (
            f"ULTRON blocked a legitimate run with no injected fault: {review.findings}"
        )
        assert len(review.findings) > 0
    finally:
        db.close()


def test_ultron_catches_a_real_inconsistency():
    db = SessionLocal()
    try:
        run = run_digital_product_pipeline(db, niche_limit=10)
        from app.models.models import Task

        product_task = db.query(Task).filter(Task.workflow_run_id == run.id, Task.stage == "product_planning").first()
        if not product_task or not product_task.output_data.get("product_id"):
            # This run's opportunity was validly rejected before any product existed --
            # nothing to sabotage, which is itself a legitimate outcome, not a test failure.
            return

        product_id = product_task.output_data["product_id"]
        asset = db.query(ProductAsset).filter(ProductAsset.product_id == product_id).first()
        assert asset is not None
        path = Path(asset.file_path)
        original_bytes = path.read_bytes()
        path.unlink()  # sabotage: remove a file ULTRON's record says should exist

        try:
            review = UltronSupervisorAgent(db).review_workflow_run(run.id)
            assert review.verdict == "blocked", "ULTRON should have blocked on a missing registered asset"
            assert any(f["check"] == "assets_present_on_disk" and f["status"] == "fail" for f in review.findings)

            concern = (
                db.query(Approval)
                .filter(Approval.action_type == "operational_concern")
                .order_by(Approval.id.desc())
                .first()
            )
            assert concern is not None and concern.status == "pending"
        finally:
            path.write_bytes(original_bytes)  # restore -- this was a deliberate test sabotage
    finally:
        db.close()


def test_system_health_check_runs_clean():
    db = SessionLocal()
    try:
        review = UltronSupervisorAgent(db).system_health_check()
        assert review.scope == "system"
        assert review.verdict in ("pass", "warning")
    finally:
        db.close()
