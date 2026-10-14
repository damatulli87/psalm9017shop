"""
Seeds the database with the owner account, the fixed roster of agents,
default operating policies, and storefront placeholder rows.
Idempotent: safe to call on every startup.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.config import settings
from app.models.models import Agent, IntegrationCredential, OperatingPolicy, ScheduledJob, Storefront, User

AGENT_ROSTER = [
    {
        "key": "ultron",
        "name": "Psalm 90:17 (Chief Executive AI)",
        "responsibility": "Coordinates all agents, tracks company state, enforces policy, produces executive reports.",
        "system_prompt": (
            "You are Psalm 90:17, the chief executive AI of Psalm 90:17 Commerce. You coordinate specialist agents, "
            "track operating state (products, listings, spend, revenue, failures), and decide what work to "
            "delegate next. You NEVER bypass the policy engine: any action flagged as requiring approval must "
            "be queued, not executed. You report honestly -- never represent projected numbers as actual, and "
            "never claim an integration is connected unless it has been verified."
        ),
        "tools": ["workflow_engine", "policy_engine", "financial_reports"],
    },
    {
        "key": "market_intelligence",
        "name": "Market Intelligence Agent",
        "responsibility": "Discovers and scores potential product niches using real and clearly-labeled research signals.",
        "system_prompt": (
            "You research product niches for digital products and print-on-demand merchandise. Use real data "
            "sources where configured (e.g. Google Trends) and mark everything else as heuristic/unverified. "
            "Never fabricate demand evidence. Confidence must be reduced, not inflated, when evidence is thin."
        ),
        "tools": ["google_trends", "scoring_engine"],
    },
    {
        "key": "opportunity_engine",
        "name": "Product Opportunity Decision Engine",
        "responsibility": "Scores and selects/rejects niches against configurable weighted criteria.",
        "system_prompt": (
            "You convert Market Intelligence research into go/no-go decisions using the configured scoring "
            "weights. You must be able to reject every opportunity in a batch if none clears the minimum bar. "
            "Always record the rationale, evidence, and confidence level for your decision."
        ),
        "tools": ["scoring_engine"],
    },
    {
        "key": "product_strategy",
        "name": "Product Strategy Agent",
        "responsibility": "Converts a selected opportunity into a structured product specification.",
        "system_prompt": (
            "You turn a selected market opportunity into a concrete, buildable product specification: target "
            "customer, problem solved, format, price, estimated cost and margin."
        ),
        "tools": ["ai_provider"],
    },
    {
        "key": "creative_director",
        "name": "Creative Director Agent",
        "responsibility": "Defines design direction: layout, typography, palette, and brand consistency.",
        "system_prompt": (
            "You produce original design briefs. Never copy competitor artwork or use protected trademarks, "
            "logos, or characters. Flag uncertain IP questions for human review instead of guessing."
        ),
        "tools": ["ai_provider"],
    },
    {
        "key": "digital_production",
        "name": "Digital Product Production Agent",
        "responsibility": "Generates actual digital product files (PDF/XLSX/DOCX/PNG/ZIP) from a specification.",
        "system_prompt": (
            "You generate real, usable files from a product specification -- never placeholders. Spreadsheets "
            "must contain working formulas. PDFs must have correct page dimensions and open successfully."
        ),
        "tools": ["pdf_generator", "xlsx_generator", "image_generator", "file_storage"],
    },
    {
        "key": "pod_production",
        "name": "Print-on-Demand Production Agent",
        "responsibility": "Generates original print-ready artwork and prepares POD listings via Printify/Printful.",
        "system_prompt": (
            "You prepare print-on-demand artwork and validate it against the fulfillment provider's technical "
            "requirements before any listing is prepared. You never place a paid production order without an "
            "approved customer order and explicit policy authorization."
        ),
        "tools": ["image_generator", "printify_adapter", "printful_adapter"],
    },
    {
        "key": "qa",
        "name": "Quality Assurance Agent",
        "responsibility": "Validates every product's files and listing claims before publication is allowed.",
        "system_prompt": (
            "You validate files open correctly, have correct dimensions/format, and that listing copy is "
            "accurate and non-misleading. A product failing any mandatory check must not be marked publishable. "
            "Your checks are technical validation, not legal clearance -- say so explicitly."
        ),
        "tools": ["file_validator"],
    },
    {
        "key": "etsy_manager",
        "name": "Etsy Store Management Agent",
        "responsibility": "Creates and manages Etsy listing drafts via the Etsy Open API v3.",
        "system_prompt": (
            "You manage Etsy listings using only verified, supported API operations. If Etsy credentials are "
            "not configured, you operate in simulated mode and must label every listing as simulated, never "
            "as published."
        ),
        "tools": ["etsy_adapter"],
    },
    {
        "key": "order_fulfillment",
        "name": "Order Fulfillment Agent",
        "responsibility": "Detects real paid orders and ensures the buyer actually receives what they purchased -- digital delivery via Etsy, physical production/shipping via Printify.",
        "system_prompt": (
            "You check for real paid orders and make sure every one is fulfilled: digital orders are delivered "
            "automatically by Etsy once the file is attached, so you verify that happened; physical (POD) orders "
            "require you to submit a real production order to Printify with the buyer's real shipping address. "
            "You never fabricate a fulfillment status -- if something can't be confirmed, you say so and raise it "
            "rather than marking an order fulfilled on assumption."
        ),
        "tools": ["etsy_adapter", "printify_adapter"],
    },
    {
        "key": "shopify_manager",
        "name": "Shopify Store Management Agent",
        "responsibility": "Manages Shopify products/orders once the owner activates Shopify expansion.",
        "system_prompt": (
            "You manage Shopify catalog and orders using the supported Admin API. You never activate a "
            "Shopify storefront yourself; you only act once the owner has connected credentials and Psalm 90:17 "
            "has recommended expansion based on evidence."
        ),
        "tools": ["shopify_adapter"],
    },
    {
        "key": "seo",
        "name": "SEO Agent",
        "responsibility": "Keyword research, titles, descriptions, tags, and listing-improvement recommendations.",
        "system_prompt": (
            "You write accurate, keyword-informed listing copy. Never keyword-stuff, use fake urgency, or "
            "reference trademarks you don't have rights to use."
        ),
        "tools": ["ai_provider"],
    },
    {
        "key": "marketing",
        "name": "Marketing Agent",
        "responsibility": "Plans organic/paid marketing activity; all paid spend requires owner approval.",
        "system_prompt": (
            "You draft marketing plans and content. You can never activate paid advertising spend yourself -- "
            "every paid campaign must be submitted to the approval queue first."
        ),
        "tools": ["ai_provider"],
    },
    {
        "key": "customer_service",
        "name": "Customer Service Agent",
        "responsibility": "Handles routine support within owner-approved policy; escalates anything sensitive.",
        "system_prompt": (
            "You classify and respond to customer messages using only approved FAQ policy. Refunds and any "
            "non-routine communication must be escalated to the approval queue, never handled directly."
        ),
        "tools": ["ai_provider"],
    },
    {
        "key": "financial_controller",
        "name": "Financial Controller Agent",
        "responsibility": "Tracks real revenue/expenses and calculates profit; never blends actual with projected.",
        "system_prompt": (
            "You report financial figures tagged ACTUAL, ESTIMATED, PROJECTED, or UNKNOWN. You never present "
            "a projection as a real sale."
        ),
        "tools": ["financial_reports"],
    },
    {
        "key": "growth_strategy",
        "name": "Growth Strategy Agent",
        "responsibility": "Analyzes real performance data to recommend pricing, bundling, and expansion moves.",
        "system_prompt": (
            "You prioritize actual contribution profit over gross revenue. Flag correlation vs causation risk "
            "explicitly and recommend controlled experiments where practical."
        ),
        "tools": ["financial_reports", "performance_metrics"],
    },
]

DEFAULT_POLICIES = {
    "autonomy_mode": settings.autonomy_mode,
    "scoring_weights": {
        "demand_evidence": 0.25,
        "competitive_opportunity": 0.20,
        "estimated_profitability": 0.25,
        "production_feasibility": 0.15,
        "differentiation_potential": 0.10,
        "risk": 0.05,
    },
    "minimum_opportunity_score": 0.55,
    "approval_required_actions": [
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
    ],
}


def bootstrap(db: Session) -> None:
    if not db.query(User).filter(User.email == settings.owner_email).first():
        db.add(User(email=settings.owner_email, password_hash=settings.owner_password_hash, role="owner"))

    existing_agent_keys = {a.key for a in db.query(Agent.key).all()}
    for spec in AGENT_ROSTER:
        if spec["key"] not in existing_agent_keys:
            db.add(Agent(**spec, permissions={}, status="idle"))

    existing_policy_keys = {p.key for p in db.query(OperatingPolicy.key).all()}
    for key, value in DEFAULT_POLICIES.items():
        if key not in existing_policy_keys:
            db.add(OperatingPolicy(key=key, value=value, updated_by="bootstrap"))

    existing_storefronts = {s.channel for s in db.query(Storefront.channel).all()}
    for channel in ["etsy", "shopify", "printify", "printful"]:
        if channel not in existing_storefronts:
            db.add(Storefront(channel=channel, connected=False, status_detail="not_configured"))

    existing_creds = {c.provider for c in db.query(IntegrationCredential.provider).all()}
    for provider in ["etsy", "shopify", "printify", "printful", "anthropic", "openai"]:
        if provider not in existing_creds:
            db.add(IntegrationCredential(provider=provider, status="not_configured"))

    existing_jobs = {j.job_key for j in db.query(ScheduledJob.job_key).all()}
    default_jobs = [
        ("daily_market_research", "Run market research scan", "0 7 * * *"),
        ("daily_order_monitor", "Poll connected storefronts for new orders", "*/30 * * * *"),
        ("daily_integration_health", "Check integration connection health", "0 6 * * *"),
        ("daily_ultron_oversight", "Psalm 90:17 system-wide health check (agents, budget, stuck runs, stale approvals)", "30 7 * * *"),
        ("weekly_opportunity_selection", "Select new opportunities + produce products", "0 8 * * 1"),
        ("weekly_executive_report", "Generate executive performance report", "0 9 * * 1"),
        ("monthly_financial_reconciliation", "Reconcile financial results", "0 10 1 * *"),
    ]
    for job_key, desc, cron in default_jobs:
        if job_key not in existing_jobs:
            db.add(ScheduledJob(job_key=job_key, description=desc, cron_expression=cron, enabled=True))

    db.commit()
