"""
Psalm 90:17 Commerce database schema (spec section 27).

Design notes:
- SQLite by default for zero-install local dev; set DATABASE_URL to a
  Postgres DSN for production (models use only portable SQLAlchemy types).
- JSON columns are used for structured-but-variable data (evidence, scores
  rationale, tool lists) rather than inventing extra join tables for an MVP.
- `actual_or_estimated` enums exist on every money-bearing row so the
  Financial Controller can never blend real and projected figures silently.
- No table stores raw API secrets. IntegrationCredential tracks connection
  *status* only; real secrets live in environment variables (see config.py).
"""
from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


class MoneyBasis(str, enum.Enum):
    ACTUAL = "ACTUAL"
    ESTIMATED = "ESTIMATED"
    PROJECTED = "PROJECTED"
    UNKNOWN = "UNKNOWN"


# ---------------------------------------------------------------- Users ----
class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(50), default="owner")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)


# --------------------------------------------------------------- Agents ----
class Agent(Base):
    __tablename__ = "agents"
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(100), unique=True)  # e.g. "market_intelligence"
    name: Mapped[str] = mapped_column(String(150))
    responsibility: Mapped[str] = mapped_column(Text)
    system_prompt: Mapped[str] = mapped_column(Text)
    tools: Mapped[list] = mapped_column(JSON, default=list)
    permissions: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(30), default="idle")  # idle/working/error/disabled
    current_task: Mapped[str | None] = mapped_column(String(255), nullable=True)
    total_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)


class AgentMemory(Base):
    __tablename__ = "agent_memories"
    id: Mapped[int] = mapped_column(primary_key=True)
    agent_key: Mapped[str] = mapped_column(String(100), index=True)
    category: Mapped[str] = mapped_column(String(30))  # business/agent/market/customer/strategic
    key: Mapped[str] = mapped_column(String(255))
    content: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AgentMessage(Base):
    __tablename__ = "agent_messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    from_agent_key: Mapped[str] = mapped_column(String(100))
    to_agent_key: Mapped[str] = mapped_column(String(100))
    mission_id: Mapped[int | None] = mapped_column(ForeignKey("missions.id"), nullable=True)
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)


# ------------------------------------------------------- Missions/Tasks ----
class Mission(Base):
    __tablename__ = "missions"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    instruction: Mapped[str] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String(50))  # owner/scheduler/ultron
    status: Mapped[str] = mapped_column(String(30), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    workflow_runs: Mapped[list["WorkflowRun"]] = relationship(back_populates="mission")


class WorkflowRun(Base):
    __tablename__ = "workflow_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    mission_id: Mapped[int | None] = mapped_column(ForeignKey("missions.id"), nullable=True)
    workflow_type: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(30), default="pending")
    current_stage: Mapped[str | None] = mapped_column(String(100), nullable=True)
    context: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    mission: Mapped[Mission | None] = relationship(back_populates="workflow_runs")
    tasks: Mapped[list["Task"]] = relationship(back_populates="workflow_run", cascade="all, delete-orphan")


class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[int] = mapped_column(primary_key=True)
    workflow_run_id: Mapped[int] = mapped_column(ForeignKey("workflow_runs.id"))
    stage: Mapped[str] = mapped_column(String(100))
    agent_key: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(30), default="pending")
    input_data: Mapped[dict] = mapped_column(JSON, default=dict)
    output_data: Mapped[dict] = mapped_column(JSON, default=dict)
    retries: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    workflow_run: Mapped[WorkflowRun] = relationship(back_populates="tasks")

    __table_args__ = (UniqueConstraint("workflow_run_id", "stage", name="uq_task_stage_per_run"),)


# -------------------------------------------------------------- Research ----
class ResearchSource(Base):
    __tablename__ = "research_sources"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150))
    source_type: Mapped[str] = mapped_column(String(50))  # google_trends/etsy_api/manual/heuristic
    is_real_data: Mapped[bool] = mapped_column(Boolean, default=False)
    url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    raw_data: Mapped[dict] = mapped_column(JSON, default=dict)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)


class MarketOpportunity(Base):
    __tablename__ = "market_opportunities"
    id: Mapped[int] = mapped_column(primary_key=True)
    workflow_run_id: Mapped[int | None] = mapped_column(ForeignKey("workflow_runs.id"), nullable=True)
    niche_title: Mapped[str] = mapped_column(String(255))
    category: Mapped[str] = mapped_column(String(20))  # digital/pod
    description: Mapped[str] = mapped_column(Text)
    evidence_summary: Mapped[dict] = mapped_column(JSON, default=dict)
    source_ids: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)

    scores: Mapped[list["OpportunityScore"]] = relationship(back_populates="opportunity")


class OpportunityScore(Base):
    __tablename__ = "opportunity_scores"
    id: Mapped[int] = mapped_column(primary_key=True)
    opportunity_id: Mapped[int] = mapped_column(ForeignKey("market_opportunities.id"))
    demand_score: Mapped[float] = mapped_column(Float)
    competition_score: Mapped[float] = mapped_column(Float)
    profitability_score: Mapped[float] = mapped_column(Float)
    feasibility_score: Mapped[float] = mapped_column(Float)
    differentiation_score: Mapped[float] = mapped_column(Float)
    risk_score: Mapped[float] = mapped_column(Float)
    weights: Mapped[dict] = mapped_column(JSON, default=dict)
    weighted_total: Mapped[float] = mapped_column(Float)
    confidence_level: Mapped[str] = mapped_column(String(20))  # low/medium/high
    rationale: Mapped[str] = mapped_column(Text)
    decision: Mapped[str] = mapped_column(String(30))  # selected/rejected/needs_more_research
    decided_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)

    opportunity: Mapped[MarketOpportunity] = relationship(back_populates="scores")


# ------------------------------------------------------------- Products ----
class ProductSpecification(Base):
    __tablename__ = "product_specifications"
    id: Mapped[int] = mapped_column(primary_key=True)
    opportunity_id: Mapped[int | None] = mapped_column(ForeignKey("market_opportunities.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(255))
    product_type: Mapped[str] = mapped_column(String(20))  # digital/pod
    target_customer: Mapped[str] = mapped_column(Text)
    # True only when target_customer actually came from a real AI provider call
    # (not the MOCK_LLM fallback). Drives whether listing copy may honestly
    # claim AI assistance -- see SEOAgent.build_listing_copy and
    # UltronSupervisorAgent.verify_ai_disclosure_accuracy.
    target_customer_is_ai: Mapped[bool] = mapped_column(Boolean, default=False)
    problem_solved: Mapped[str] = mapped_column(Text)
    format: Mapped[str] = mapped_column(String(50))  # pdf/xlsx/docx/zip/tshirt/mug/...
    design_brief: Mapped[dict] = mapped_column(JSON, default=dict)
    recommended_price_usd: Mapped[float] = mapped_column(Float, default=0.0)
    estimated_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    estimated_margin_usd: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(30), default="planned")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)

    assets: Mapped[list["ProductAsset"]] = relationship(back_populates="product", cascade="all, delete-orphan")
    versions: Mapped[list["ProductVersion"]] = relationship(back_populates="product", cascade="all, delete-orphan")
    qa_results: Mapped[list["QAResult"]] = relationship(back_populates="product", cascade="all, delete-orphan")


class ProductAsset(Base):
    __tablename__ = "product_assets"
    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("product_specifications.id"))
    asset_type: Mapped[str] = mapped_column(String(30))  # pdf/xlsx/docx/png/zip
    file_path: Mapped[str] = mapped_column(String(500))
    file_size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    checksum_sha256: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)

    product: Mapped[ProductSpecification] = relationship(back_populates="assets")


class ProductVersion(Base):
    __tablename__ = "product_versions"
    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("product_specifications.id"))
    version_number: Mapped[int] = mapped_column(Integer, default=1)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)

    product: Mapped[ProductSpecification] = relationship(back_populates="versions")


class QAResult(Base):
    __tablename__ = "qa_results"
    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("product_specifications.id"))
    check_name: Mapped[str] = mapped_column(String(150))
    passed: Mapped[bool] = mapped_column(Boolean)
    details: Mapped[str] = mapped_column(Text, default="")
    checked_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)

    product: Mapped[ProductSpecification] = relationship(back_populates="qa_results")


# ---------------------------------------------------------- Marketplace ----
class Storefront(Base):
    __tablename__ = "storefronts"
    id: Mapped[int] = mapped_column(primary_key=True)
    channel: Mapped[str] = mapped_column(String(30), unique=True)  # etsy/shopify/printify/printful
    connected: Mapped[bool] = mapped_column(Boolean, default=False)
    shop_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status_detail: Mapped[str] = mapped_column(String(255), default="not_configured")
    connected_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class MarketplaceListing(Base):
    __tablename__ = "marketplace_listings"
    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("product_specifications.id"))
    storefront_channel: Mapped[str] = mapped_column(String(30))
    external_listing_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text)
    price_usd: Mapped[float] = mapped_column(Float)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=True)  # True until a real API call succeeds
    status: Mapped[str] = mapped_column(String(30), default="draft")  # draft/pending_approval/approved/published/rejected
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Order(Base):
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    storefront_channel: Mapped[str] = mapped_column(String(30))
    external_order_id: Mapped[str] = mapped_column(String(100))
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), nullable=True)
    order_total_usd: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(30), default="received")
    raw_data: Mapped[dict] = mapped_column(JSON, default=dict)
    placed_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)

    __table_args__ = (UniqueConstraint("storefront_channel", "external_order_id", name="uq_order_per_channel"),)


class FulfillmentEvent(Base):
    __tablename__ = "fulfillment_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"))
    provider: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(50))
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    tracking_info: Mapped[str] = mapped_column(String(255), default="")
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)


class Customer(Base):
    __tablename__ = "customers"
    id: Mapped[int] = mapped_column(primary_key=True)
    storefront_channel: Mapped[str] = mapped_column(String(30))
    external_customer_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    email_hash: Mapped[str] = mapped_column(String(64))  # never store raw customer email
    display_name: Mapped[str] = mapped_column(String(150), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)


# ----------------------------------------------------------- Financials ----
class Transaction(Base):
    __tablename__ = "transactions"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"), nullable=True)
    type: Mapped[str] = mapped_column(String(30))  # sale/refund/fee/expense
    amount_usd: Mapped[float] = mapped_column(Float)
    basis: Mapped[str] = mapped_column(String(20), default=MoneyBasis.UNKNOWN.value)
    description: Mapped[str] = mapped_column(String(255), default="")
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)


class Expense(Base):
    __tablename__ = "expenses"
    id: Mapped[int] = mapped_column(primary_key=True)
    category: Mapped[str] = mapped_column(String(50))  # ai_api/hosting/subscription/advertising/pod_production/other
    amount_usd: Mapped[float] = mapped_column(Float)
    basis: Mapped[str] = mapped_column(String(20), default=MoneyBasis.ACTUAL.value)
    description: Mapped[str] = mapped_column(String(255), default="")
    workflow_run_id: Mapped[int | None] = mapped_column(ForeignKey("workflow_runs.id"), nullable=True)
    agent_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    incurred_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)


class MarketingCampaign(Base):
    __tablename__ = "marketing_campaigns"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    channel: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(30), default="draft")  # draft/pending_approval/approved/active/paused
    budget_usd: Mapped[float] = mapped_column(Float, default=0.0)
    spent_usd: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)


# ------------------------------------------------- Approvals & Policies ----
class Approval(Base):
    __tablename__ = "approvals"
    id: Mapped[int] = mapped_column(primary_key=True)
    action_type: Mapped[str] = mapped_column(String(100))  # publish_listing/paid_ad/refund/new_subscription/...
    summary: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    estimated_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    risk_level: Mapped[str] = mapped_column(String(20), default="low")
    status: Mapped[str] = mapped_column(String(30), default="pending")  # pending/approved/rejected/changes_requested
    requested_by_agent: Mapped[str] = mapped_column(String(100))
    requested_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    decided_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")


class OperatingPolicy(Base):
    __tablename__ = "operating_policies"
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(150), unique=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)
    updated_by: Mapped[str] = mapped_column(String(100), default="system")


class IntegrationCredential(Base):
    __tablename__ = "integration_credentials"
    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(50), unique=True)
    status: Mapped[str] = mapped_column(String(30), default="not_configured")
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)


class ScheduledJob(Base):
    __tablename__ = "scheduled_jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    job_key: Mapped[str] = mapped_column(String(100), unique=True)
    description: Mapped[str] = mapped_column(String(255), default="")
    cron_expression: Mapped[str] = mapped_column(String(100))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_status: Mapped[str] = mapped_column(String(30), default="never_run")
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    event_type: Mapped[str] = mapped_column(String(100))
    actor: Mapped[str] = mapped_column(String(100))
    summary: Mapped[str] = mapped_column(String(500))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)


class AIUsageRecord(Base):
    __tablename__ = "ai_usage_records"
    id: Mapped[int] = mapped_column(primary_key=True)
    agent_key: Mapped[str] = mapped_column(String(100))
    provider: Mapped[str] = mapped_column(String(50))  # anthropic/openai/mock
    model: Mapped[str] = mapped_column(String(100))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    is_mock: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)


class BusinessExperiment(Base):
    __tablename__ = "business_experiments"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    hypothesis: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="proposed")
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    outcome: Mapped[str] = mapped_column(Text, default="")
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)


class PerformanceMetric(Base):
    __tablename__ = "performance_metrics"
    id: Mapped[int] = mapped_column(primary_key=True)
    metric_key: Mapped[str] = mapped_column(String(100))
    scope: Mapped[str] = mapped_column(String(30))  # agent/product/workflow/business
    scope_id: Mapped[str] = mapped_column(String(100))
    value: Mapped[float] = mapped_column(Float)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)


class OAuthToken(Base):
    """
    Persisted OAuth tokens for marketplace integrations (Etsy et al.).
    Unlike static API keys, these are obtained through an interactive
    browser flow and refresh over time, so they can't live in a static
    .env file -- they're stored here with the token fields encrypted at
    rest (see app/integrations/crypto.py), keyed off SECRET_KEY. Never
    exposed through any API response.
    """
    __tablename__ = "oauth_tokens"
    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(50), unique=True)
    access_token_encrypted: Mapped[str] = mapped_column(Text)
    refresh_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    scope: Mapped[str] = mapped_column(String(255), default="")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    obtained_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc, onupdate=now_utc)


class SupervisionReview(Base):
    """
    Psalm 90:17's independent verification record (spec section 4: 'monitoring
    execution', 'identifying operational problems'). Each row is the result
    of re-deriving a conclusion from raw data and comparing it against what
    the responsible agent reported -- not an LLM opinion. `findings` holds
    the full list of individual checks with their own pass/warn/fail detail
    so a "blocked" verdict is always explainable.
    """
    __tablename__ = "supervision_reviews"
    id: Mapped[int] = mapped_column(primary_key=True)
    scope: Mapped[str] = mapped_column(String(30))  # workflow_run / system
    scope_id: Mapped[str] = mapped_column(String(100))
    verdict: Mapped[str] = mapped_column(String(20))  # pass / warning / blocked
    summary: Mapped[str] = mapped_column(String(500))
    findings: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)
