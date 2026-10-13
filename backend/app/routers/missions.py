from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.security import get_current_user
from app.database import get_db
from app.models.models import Mission, Task, WorkflowRun
from app.orchestration.workflow_engine import run_digital_product_pipeline

router = APIRouter(prefix="/missions", tags=["missions"])


class RunPipelineRequest(BaseModel):
    title: str = "Run digital product discovery pipeline"
    niche_limit: int = 8


@router.post("/run-digital-pipeline")
def run_pipeline(body: RunPipelineRequest, db: Session = Depends(get_db), user=Depends(get_current_user)):
    mission = Mission(title=body.title, instruction="run_digital_product_pipeline", created_by="owner",
                       status="running")
    db.add(mission)
    db.commit()
    db.refresh(mission)

    run = run_digital_product_pipeline(db, mission_id=mission.id, niche_limit=body.niche_limit)

    mission.status = run.status
    from datetime import datetime, timezone
    mission.completed_at = datetime.now(timezone.utc)
    db.commit()

    return {"mission_id": mission.id, "workflow_run_id": run.id, "status": run.status,
            "current_stage": run.current_stage, "error": run.error}


@router.get("")
def list_missions(db: Session = Depends(get_db), user=Depends(get_current_user)):
    missions = db.query(Mission).order_by(Mission.id.desc()).limit(100).all()
    return [
        {"id": m.id, "title": m.title, "status": m.status, "created_by": m.created_by,
         "created_at": m.created_at, "completed_at": m.completed_at}
        for m in missions
    ]


@router.get("/workflow-runs/{run_id}")
def get_workflow_run(run_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    run = db.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
    if not run:
        return {"error": "not found"}
    tasks = db.query(Task).filter(Task.workflow_run_id == run_id).order_by(Task.id).all()
    return {
        "id": run.id, "workflow_type": run.workflow_type, "status": run.status,
        "current_stage": run.current_stage, "error": run.error,
        "started_at": run.started_at, "completed_at": run.completed_at,
        "tasks": [
            {"stage": t.stage, "agent_key": t.agent_key, "status": t.status,
             "output": t.output_data, "error": t.error}
            for t in tasks
        ],
    }


@router.get("/workflow-runs")
def list_workflow_runs(db: Session = Depends(get_db), user=Depends(get_current_user)):
    runs = db.query(WorkflowRun).order_by(WorkflowRun.id.desc()).limit(50).all()
    return [
        {"id": r.id, "workflow_type": r.workflow_type, "status": r.status, "current_stage": r.current_stage,
         "started_at": r.started_at, "completed_at": r.completed_at}
        for r in runs
    ]
