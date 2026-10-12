# Architecture

## Stack

- **Backend**: Python 3.13, FastAPI, SQLAlchemy 2.0, Alembic, APScheduler.
  SQLite by default (zero-install local dev); set `DATABASE_URL` to a
  Postgres DSN for production -- every model uses portable SQLAlchemy types,
  no SQLite-specific features.
- **Frontend**: Next.js 16 (App Router) + TypeScript + Tailwind CSS v4.
  Client-rendered behind a JWT-gated layout; no server-side data fetching of
  authenticated content (keeps the API the single source of truth and
  credentials out of server components).
- **Orchestration**: a hand-rolled, DB-backed durable workflow engine
  (`backend/app/orchestration/workflow_engine.py`), not LangGraph. See
  "Why not LangGraph" below.
- **AI**: `backend/app/integrations/ai_providers.py` routes to Anthropic or
  OpenAI when API keys are configured, with per-call cost tracking written
  to `AIUsageRecord` and `Expense`. With no keys configured, every call
  returns a clearly-labeled `MOCK_LLM` structural placeholder so the rest of
  the pipeline remains fully exercisable.

## Why not LangGraph

The spec allows "LangGraph or another production-capable agent orchestration
framework." LangGraph installs and runs fine here, but the actual
requirement that matters for a side-business backend ("workflows survive
restarts", "prevent overlapping jobs from creating duplicate products") is
really a durability/idempotency property, not a graph-execution property.
`workflow_engine.py` gets that directly and verifiably: every stage is a
`Task` row written to the database *before* the stage runs and finalized
*after* it completes, so `resume_after_approval()` can reconstruct exactly
where a run paused (at `authorization`) and continue it without re-running
(and re-charging, or re-publishing) earlier stages. Agents are plain Python
classes with no framework coupling, so swapping in LangGraph later -- e.g. to
get branching/parallel fan-out for multi-niche batches -- does not require
rewriting agent logic.

## Data flow (digital product pipeline)

```
MarketIntelligenceAgent.research_candidates()
  -> ResearchSource rows (is_real_data=True when Google Trends answered)
  -> MarketOpportunity rows

OpportunityDecisionEngine.select_best()
  -> OpportunityScore rows (weighted, configurable, logged rationale)
  -> picks best "selected" opportunity, or returns None (valid rejection)

ProductStrategyAgent.build_spec()        -> ProductSpecification
CreativeDirectorAgent.create_design_brief() -> design_brief JSON on the spec
DigitalProductionAgent.produce()         -> real PDF/XLSX + PNG preview + ZIP
                                             on disk, ProductAsset rows with
                                             SHA-256 checksums
QAAgent.run_checks()                     -> QAResult rows; product.status
                                             only becomes "qa_passed" if every
                                             mandatory check passes
SEOAgent.build_listing_copy()
EtsyManagerAgent.prepare_listing_draft()  -> MarketplaceListing (is_simulated
                                             =True until Etsy is connected)
policy_engine.authorize("publish_listing") -> Approval row (SUPERVISED mode:
                                              always required)
   ... workflow pauses at status=awaiting_approval ...
[owner decides via API/UI]
resume_after_approval()                  -> publication stage, then stubs
                                             the not-yet-built marketing/
                                             sales-monitoring/optimization
                                             stages with an honest note
                                             rather than skipping silently
```

## Psalm 90:17 is a verifier, not a coordinator-in-name-only

`backend/app/agents/ultron.py` re-derives conclusions from raw rows (QA
results, registered file paths, opportunity scores, approval records) and
compares them against what the responsible agent/stage reported, rather
than trusting a status column. Two checkpoints are embedded directly in
`workflow_engine.py` (after opportunity selection, after QA) and can halt a
run with `blocked_by_oversight`; a full review runs on every exit path
(including both branches of `resume_after_approval`), and a system-wide
sweep runs daily via the scheduler. A `blocked` verdict opens a real
`Approval` row -- Psalm 90:17 can raise a concern but, like every other agent,
cannot resolve it itself; only the owner can. See AGENTS.md for the full
check list and `backend/tests/test_ultron_oversight.py` for the test that
proves it actually catches a deliberately-introduced inconsistency rather
than rubber-stamping.

## Policy engine is not an agent

`backend/app/policy/engine.py` contains no AI calls. `authorize()` is the
single choke point: hard-coded `ALWAYS_REQUIRES_APPROVAL` action types,
budget checks against `app/config.py` caps, and the current
`autonomy_mode` read from the `operating_policies` table. Agents call it;
they cannot bypass it, and nothing in the codebase lets an agent write to
`OperatingPolicy` rows that affect its own authorization (only the owner-
authenticated `/settings/policies` endpoint can).

## Database

30 tables matching spec section 27 exactly (Users, Agents, Missions, Tasks,
WorkflowRuns, AgentMessages, AgentMemories, ResearchSources,
MarketOpportunities, OpportunityScores, ProductSpecifications,
ProductAssets, ProductVersions, QAResults, Storefronts,
MarketplaceListings, Orders, FulfillmentEvents, Customers, Transactions,
Expenses, MarketingCampaigns, Approvals, OperatingPolicies,
IntegrationCredentials, ScheduledJobs, AuditEvents, AIUsageRecords,
BusinessExperiments, PerformanceMetrics). See
`backend/app/models/models.py` for the full schema and
`backend/alembic/versions/` for the migration.

Money-bearing rows (`Transaction`, `Expense`) carry a `basis` column
(`ACTUAL`/`ESTIMATED`/`PROJECTED`/`UNKNOWN`) so the Financial Controller
can never report a blended number.

## Known architectural simplifications (vs. the full spec)

- Single-owner auth, not full RBAC with multiple roles.
- Agent memory table exists and is written to by agents' audit logs, but
  there is no vector/semantic retrieval layer yet -- it's queryable by
  key/category only.
- No Redis / message queue; the scheduler and workflow engine run in-process
  via APScheduler. Fine at this scale (a handful of workflow runs a day);
  would need a real task queue (Celery/RQ) before running multiple
  concurrent workers.
- No object storage adapter (S3) yet -- `app/integrations/file_storage.py`
  isolates local-disk storage behind the one function (`register_asset`)
  that would need to change.
