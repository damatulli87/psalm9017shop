# Agents

All 15 agents below are seeded into the `agents` DB table by
`backend/app/bootstrap.py` on first startup, and are visible live in the
command center's **AI Agent Network** screen (status, current task, cost,
AI call count pulled from real `AuditEvent`/`AIUsageRecord` rows).

Every agent class inherits `BaseAgent` (`backend/app/agents/base.py`), which
gives it: identity loaded from its DB row, `run_with_retries()` (retry +
error capture), `log()` (writes to `AuditEvent`), and `request_approval()`
(the *only* way an agent can ask for something sensitive -- it calls the
independent policy engine, never grants itself anything).

| Key | Name | Built? | File |
|---|---|---|---|
| `ultron` | Chief Executive AI | Yes -- real independent oversight/verification layer (see below), plus coordination via the workflow engine + chat router | `app/agents/ultron.py`, `app/orchestration/workflow_engine.py`, `app/routers/chat.py` |
| `market_intelligence` | Market Intelligence Agent | Yes -- real Google Trends signal | `app/agents/market_intelligence.py` |
| `opportunity_engine` | Product Opportunity Decision Engine | Yes -- configurable weighted scoring, can reject all | `app/agents/opportunity_engine.py` |
| `product_strategy` | Product Strategy Agent | Yes | `app/agents/product_strategy.py` |
| `creative_director` | Creative Director Agent | Yes (design brief only, no image-gen model wired) | `app/agents/creative_director.py` |
| `digital_production` | Digital Product Production Agent | Yes -- real PDF/XLSX/PNG/ZIP | `app/agents/digital_production.py` |
| `pod_production` | Print-on-Demand Production Agent | **Not implemented** | seeded only; no code yet |
| `qa` | Quality Assurance Agent | Yes -- real file validation | `app/agents/qa.py` |
| `etsy_manager` | Etsy Store Management Agent | Adapter built (real OAuth/PKCE + listing-create request), runs SIMULATED until credentials added | `app/agents/etsy_manager.py`, `app/integrations/etsy.py` |
| `shopify_manager` | Shopify Store Management Agent | **Not implemented** | seeded only; no code yet |
| `seo` | SEO Agent | Yes -- rule-based, with a banned-phrase filter | `app/agents/seo.py` |
| `marketing` | Marketing Agent | **Not implemented** | seeded only |
| `customer_service` | Customer Service Agent | **Not implemented** | seeded only |
| `financial_controller` | Financial Controller Agent | Yes -- real ledger reads, ACTUAL/PROJECTED/UNKNOWN separated | `app/agents/financial_controller.py` |
| `growth_strategy` | Growth Strategy Agent | **Not implemented** (needs real sales history to analyze) | seeded only |

## Why some agents are "seeded only"

Spec section 3 requires every agent to have an identity, prompt, tools, and
permissions -- all 15 have that now (queryable at `GET /agents`). Writing the
*execution logic* for POD/Shopify/marketing/customer-service/growth-strategy
before there's a connected marketplace or a single real sale is where this
build draws the line for now: there is nothing real for those agents to do
yet, and building a fake flow for "a customer service agent that answers
real customer messages" with no real customers would violate the project's
own "do not fabricate activity" rule. See [PROGRESS.md](PROGRESS.md) for the
dependency each one is blocked on.

## ULTRON as an independent verifier, not a report generator

Spec section 4 asks for a "boss" that monitors execution and identifies
operational problems. `app/agents/ultron.py` implements this as real,
deterministic verification -- no LLM call, same philosophy as the policy
engine: re-derive the conclusion from raw data and compare it against what
the responsible agent reported, rather than trusting a status flag.

Checks it runs:
- **`score_recomputation` / `decision_consistency`** -- recomputes an
  opportunity's weighted score from its component scores and the configured
  weights, and checks the stored decision is actually consistent with the
  minimum-score policy.
- **`evidence_quality`** -- flags (warns, doesn't block) a selection made
  without verified real demand data.
- **`qa_status_consistency`** -- recomputes pass/fail from the raw
  `QAResult` rows and checks it matches `product.status`.
- **`assets_present_on_disk`** -- re-opens every registered file path on
  disk; a product can't claim to have deliverables that don't exist.
- **`publish_authorization`** -- any listing in a gated state must have a
  real, owner-approved `Approval` row referencing it, or ULTRON treats that
  as a policy-engine bypass.
- **`no_failed_tasks` / `workflow_cost_cap` / `agent_health`** -- per-run
  sanity checks against `Task`, `Expense`, and `Agent.status`.
- System-wide (`system_health_check`, scheduled daily at 7:30am): agent
  fleet health, month-to-date spend vs. the startup budget ceiling, stuck
  "running" workflows, and stale pending approvals.

Two checkpoints run *inside* the pipeline itself (after opportunity
selection, after QA) and can halt the run with status
`blocked_by_oversight` before any further stage executes; a final review
runs on every exit path. A `blocked` verdict opens a real `Approval` row
(`action_type="operational_concern"`) -- ULTRON raises concerns, it does
not resolve them itself. Verified in `backend/tests/test_ultron_oversight.py`:
one test confirms it doesn't false-positive on a clean run, another
deliberately deletes a registered file and confirms ULTRON catches it and
escalates. Visible in the command center's **ULTRON Oversight** screen.

## Model routing

`app/integrations/ai_providers.py`: `complexity="routine"` calls
`default_model_routine` (`claude-haiku-4-5-20251001`), `complexity="complex"`
calls `default_model_complex` (`claude-opus-5`). Every call's token usage
and computed cost is written to `AIUsageRecord` and, if non-zero, to
`Expense(category="ai_api", basis="ACTUAL")` -- so the budget engine's
monthly AI cap is enforced against real spend the moment real keys are
added, with no code changes required.
