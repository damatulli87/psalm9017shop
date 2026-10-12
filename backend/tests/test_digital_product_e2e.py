"""
Required end-to-end test (spec section 33, "REQUIRED DIGITAL PRODUCT TEST"):
research -> select -> spec -> produce real files -> validate -> Etsy draft
-> submit for approval -> everything recorded in the DB.
"""
from __future__ import annotations

from pathlib import Path

from app.database import SessionLocal
from app.models.models import Approval, MarketplaceListing, ProductAsset, ProductSpecification, QAResult, Task, WorkflowRun
from app.orchestration.workflow_engine import run_digital_product_pipeline


def test_digital_product_pipeline_end_to_end():
    db = SessionLocal()
    try:
        run = run_digital_product_pipeline(db, niche_limit=10)

        assert isinstance(run, WorkflowRun)
        assert run.status in ("awaiting_approval", "completed", "completed_no_opportunity"), run.status

        if run.status == "completed_no_opportunity":
            # Valid outcome per spec section 5: the engine may reject every opportunity.
            print("No opportunity cleared the bar -- valid rejection outcome, not a failure.")
            return

        tasks = db.query(Task).filter(Task.workflow_run_id == run.id).all()
        stages_done = {t.stage for t in tasks}
        assert {"research", "opportunity_selection", "product_planning", "creative_direction",
                "production", "quality_assurance", "listing_creation", "authorization"} <= stages_done

        product_task = next(t for t in tasks if t.stage == "product_planning")
        product_id = product_task.output_data["product_id"]
        product = db.query(ProductSpecification).filter(ProductSpecification.id == product_id).first()
        assert product is not None
        assert product.status == "qa_passed", f"Product status was {product.status}, expected qa_passed"

        assets = db.query(ProductAsset).filter(ProductAsset.product_id == product.id).all()
        assert len(assets) >= 3, "Expected main file + preview + zip at minimum"
        for asset in assets:
            p = Path(asset.file_path)
            assert p.exists(), f"Asset file missing on disk: {p}"
            assert p.stat().st_size > 0, f"Asset file is empty: {p}"

        qa_results = db.query(QAResult).filter(QAResult.product_id == product.id).all()
        assert len(qa_results) >= 4
        assert all(r.passed for r in qa_results), [r.check_name for r in qa_results if not r.passed]

        listing = db.query(MarketplaceListing).filter(MarketplaceListing.product_id == product.id).first()
        assert listing is not None
        assert listing.status in ("pending_approval", "approved", "published_simulated", "published")

        approval = db.query(Approval).filter(Approval.action_type == "publish_listing").order_by(
            Approval.id.desc()
        ).first()
        assert approval is not None
        assert approval.status == "pending"

        print(f"E2E OK: product #{product.id} '{product.title}' ({product.format}) -> "
              f"listing #{listing.id} -> approval #{approval.id} pending owner decision.")
    finally:
        db.close()


if __name__ == "__main__":
    test_digital_product_pipeline_end_to_end()
    print("PASSED")
