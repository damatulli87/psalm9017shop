from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.security import get_current_user
from app.config import settings
from app.database import get_db
from app.models.models import IntegrationCredential, OperatingPolicy

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/policies")
def list_policies(db: Session = Depends(get_db), user=Depends(get_current_user)):
    rows = db.query(OperatingPolicy).all()
    return [{"key": r.key, "value": r.value, "version": r.version, "updated_at": r.updated_at} for r in rows]


class PolicyUpdate(BaseModel):
    value: dict | list | str | float | int | bool


@router.put("/policies/{key}")
def update_policy(key: str, body: PolicyUpdate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    row = db.query(OperatingPolicy).filter(OperatingPolicy.key == key).first()
    if not row:
        row = OperatingPolicy(key=key, value=body.value, updated_by=user.email)
        db.add(row)
    else:
        row.value = body.value
        row.version += 1
        row.updated_by = user.email
    db.commit()
    return {"key": key, "value": row.value, "version": row.version}


@router.get("/integrations")
def integration_status(db: Session = Depends(get_db), user=Depends(get_current_user)):
    from app.integrations import oauth_store

    rows = db.query(IntegrationCredential).all()
    etsy_connected = oauth_store.get_valid_etsy_token(db) is not None
    configured_map = {
        "etsy": settings.etsy_configured,
        "shopify": settings.shopify_configured,
        "printify": settings.printify_configured,
        "printful": settings.printful_configured,
        "anthropic": settings.anthropic_configured,
        "openai": settings.openai_configured,
    }
    status_overrides = {"etsy": "connected" if etsy_connected else None}
    return [
        {
            "provider": r.provider,
            "status": status_overrides.get(r.provider) or ("configured" if configured_map.get(r.provider) else "awaiting_configuration"),
            "last_verified_at": r.last_verified_at,
        }
        for r in rows
    ]


@router.get("/budget")
def budget(user=Depends(get_current_user)):
    return {
        "startup_budget_ceiling_usd": settings.startup_budget_ceiling_usd,
        "monthly_ai_budget_usd": settings.monthly_ai_budget_usd,
        "monthly_image_gen_budget_usd": settings.monthly_image_gen_budget_usd,
        "advertising_budget_usd": settings.advertising_budget_usd,
        "advertising_enabled": settings.advertising_enabled,
        "max_spend_per_action_usd": settings.max_spend_per_action_usd,
        "max_spend_per_workflow_usd": settings.max_spend_per_workflow_usd,
        "max_concurrent_agent_jobs": settings.max_concurrent_agent_jobs,
        "daily_product_generation_limit": settings.daily_product_generation_limit,
    }
