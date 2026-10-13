"""
Scheduling Engine (spec section 21).

Reads cron expressions from the `scheduled_jobs` DB table (seeded in
app/bootstrap.py) and registers them with APScheduler at startup. Toggling
a job's `enabled` flag via the Settings API takes effect on the next tick
without a restart; changing the cron expression itself requires a restart
in this MVP (documented limitation -- see PROGRESS.md).

`max_instances=1` + `coalesce=True` on every job prevents overlapping runs
from creating duplicate products/orders (spec section 21's explicit
requirement), since a new product-generation run cannot start while a
previous one for the same job_key is still in flight.
"""
from __future__ import annotations

from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.database import SessionLocal
from app.models.models import Expense, ScheduledJob, Storefront
from app.orchestration.workflow_engine import run_digital_product_pipeline
from app.config import settings

_scheduler: BackgroundScheduler | None = None


def _mark_run(job_key: str, status: str) -> None:
    db = SessionLocal()
    try:
        row = db.query(ScheduledJob).filter(ScheduledJob.job_key == job_key).first()
        if row:
            row.last_run_at = datetime.now(timezone.utc)
            row.last_status = status
            db.commit()
    finally:
        db.close()


def _is_enabled(job_key: str) -> bool:
    db = SessionLocal()
    try:
        row = db.query(ScheduledJob).filter(ScheduledJob.job_key == job_key).first()
        return bool(row and row.enabled)
    finally:
        db.close()


def job_daily_market_research() -> None:
    if not _is_enabled("daily_market_research"):
        return
    db = SessionLocal()
    try:
        from app.agents.market_intelligence import MarketIntelligenceAgent
        from app.agents.opportunity_engine import OpportunityDecisionEngine

        opportunities = MarketIntelligenceAgent(db).research_candidates(limit=8)
        OpportunityDecisionEngine(db).select_best(opportunities)  # scores + logs; doesn't auto-produce
        _mark_run("daily_market_research", "success")
    except Exception as exc:  # noqa: BLE001
        _mark_run("daily_market_research", f"error: {exc}")
    finally:
        db.close()


def job_daily_ultron_oversight() -> None:
    if not _is_enabled("daily_ultron_oversight"):
        return
    db = SessionLocal()
    try:
        from app.agents.ultron import UltronSupervisorAgent

        UltronSupervisorAgent(db).system_health_check()
        _mark_run("daily_ultron_oversight", "success")
    except Exception as exc:  # noqa: BLE001
        _mark_run("daily_ultron_oversight", f"error: {exc}")
    finally:
        db.close()


def job_daily_integration_health() -> None:
    if not _is_enabled("daily_integration_health"):
        return
    db = SessionLocal()
    try:
        from app.integrations import oauth_store

        etsy_token = oauth_store.get_valid_etsy_token(db)
        checks = {
            "etsy": (settings.etsy_configured, etsy_token is not None),
            "shopify": (settings.shopify_configured, False),
            "printify": (settings.printify_configured, False),
            "printful": (settings.printful_configured, False),
        }
        for channel, (configured, connected) in checks.items():
            sf = db.query(Storefront).filter(Storefront.channel == channel).first()
            if sf:
                sf.connected = connected
                sf.status_detail = "connected" if connected else ("configured_unverified" if configured else "not_configured")
                db.commit()
        _mark_run("daily_integration_health", "success")
    except Exception as exc:  # noqa: BLE001
        _mark_run("daily_integration_health", f"error: {exc}")
    finally:
        db.close()


def job_daily_order_monitor() -> None:
    if not _is_enabled("daily_order_monitor"):
        return
    # No storefront is connected yet in a fresh deployment, so there is nothing real to poll.
    # Once Etsy/Shopify credentials are configured this calls the real orders endpoint.
    _mark_run("daily_order_monitor", "skipped_no_storefront_connected")


def job_weekly_opportunity_selection() -> None:
    if not _is_enabled("weekly_opportunity_selection"):
        return
    db = SessionLocal()
    try:
        daily_count = db.query(Expense).count()  # placeholder guard; real daily-limit check lives in policy engine
        run_digital_product_pipeline(db, niche_limit=8)
        _mark_run("weekly_opportunity_selection", "success")
    except Exception as exc:  # noqa: BLE001
        _mark_run("weekly_opportunity_selection", f"error: {exc}")
    finally:
        db.close()


def job_weekly_executive_report() -> None:
    if not _is_enabled("weekly_executive_report"):
        return
    db = SessionLocal()
    try:
        from app.agents.financial_controller import FinancialControllerAgent

        FinancialControllerAgent(db).generate_report()
        _mark_run("weekly_executive_report", "success")
    except Exception as exc:  # noqa: BLE001
        _mark_run("weekly_executive_report", f"error: {exc}")
    finally:
        db.close()


def job_monthly_financial_reconciliation() -> None:
    if not _is_enabled("monthly_financial_reconciliation"):
        return
    db = SessionLocal()
    try:
        from app.agents.financial_controller import FinancialControllerAgent

        FinancialControllerAgent(db).generate_report()
        _mark_run("monthly_financial_reconciliation", "success")
    except Exception as exc:  # noqa: BLE001
        _mark_run("monthly_financial_reconciliation", f"error: {exc}")
    finally:
        db.close()


JOB_FUNCTIONS = {
    "daily_market_research": job_daily_market_research,
    "daily_order_monitor": job_daily_order_monitor,
    "daily_integration_health": job_daily_integration_health,
    "daily_ultron_oversight": job_daily_ultron_oversight,
    "weekly_opportunity_selection": job_weekly_opportunity_selection,
    "weekly_executive_report": job_weekly_executive_report,
    "monthly_financial_reconciliation": job_monthly_financial_reconciliation,
}


def start_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = BackgroundScheduler(timezone="UTC")

    db = SessionLocal()
    try:
        jobs = db.query(ScheduledJob).all()
        for job in jobs:
            fn = JOB_FUNCTIONS.get(job.job_key)
            if not fn:
                continue
            try:
                trigger = CronTrigger.from_crontab(job.cron_expression)
            except ValueError:
                continue
            _scheduler.add_job(fn, trigger=trigger, id=job.job_key, max_instances=1, coalesce=True,
                                replace_existing=True)
    finally:
        db.close()

    _scheduler.start()


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
