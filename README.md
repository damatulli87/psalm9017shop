# ULTRON Commerce

An AI-managed, mostly-autonomous e-commerce operating system: a multi-agent
backend that researches product niches, generates real digital products,
validates them, prepares marketplace listings, and routes anything
money-spending or publish-facing through an owner approval queue -- plus a
command-center dashboard to supervise and steer it.

**Status: working MVP engine + command center, not a finished production
business.** See [PROGRESS.md](PROGRESS.md) for the honest completed/not-yet-
completed checklist. Read that file before assuming any capability below is
live end-to-end on a real marketplace.

## What actually works right now

- A durable, DB-backed workflow that performs, for real:
  **research → score/select → write a product spec → generate real PDF/XLSX
  files + a PNG preview + a ZIP package → QA-validate every file → draft an
  Etsy listing → queue it for your approval → publish (simulated until Etsy
  credentials are added) once you approve.**
- Real market signal: live Google Trends data (no API key required) feeds
  the opportunity scorer. Etsy-specific competitive data is explicitly
  marked **BLOCKED** until you connect Etsy credentials -- it is never
  guessed.
- A policy/approval engine and budget ledger that are *plain Python*, not
  agent reasoning -- agents cannot grant themselves permission or spend past
  the configured caps.
- **ULTRON actually supervises the other agents.** It independently
  re-derives conclusions from raw data (did QA really pass? do the files
  really exist? does the score really add up? is there really an approved
  Approval behind this listing?) rather than trusting self-reported status,
  at two checkpoints inside every pipeline run plus a daily system-wide
  sweep. A real inconsistency gets the run blocked and opens an entry in
  your Approval Center. Verified with a test that deliberately deletes a
  product file and confirms ULTRON catches it.
- 15 named agents (see [AGENTS.md](AGENTS.md)) with persistent identity,
  system prompts, status, cost tracking, and audit logging in Postgres/SQLite.
- A modern dark command center (Next.js) with live Dashboard, ULTRON
  Oversight, Agent Network (featuring an illustrated "Factory Floor" view of
  the real pipeline), Mission Control, Product Factory, Marketplace Center,
  Financial Command Center, Approval Center, Activity Monitor, Executive AI
  Chat, and Settings.

## What is explicitly NOT done yet

POD production, Shopify, real Etsy publishing, paid marketing execution,
real sales monitoring, and the self-improvement engine are not built or are
stubbed with an honest "not yet implemented" marker. Full list in
[PROGRESS.md](PROGRESS.md).

## Quickstart (local dev)

### Backend
```bash
cd backend
python -m venv venv
source venv/Scripts/activate      # Windows Git Bash; use venv\Scripts\activate.bat on cmd
pip install -r requirements.txt
cp .env.example .env               # fill in real keys only if you have them
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```
API docs: http://localhost:8000/docs

### Frontend
```bash
cd frontend
npm install
cp .env.local.example .env.local   # already created with http://localhost:8000
npm run dev
```
Command center: http://localhost:3000 — dev login is
`owner@example.com` / `ultron-dev-only` (rotate via `/auth/change-password`
before any real deployment; see [SECURITY.md](SECURITY.md)).

### Run the first milestone yourself
1. Log in.
2. Go to **Mission Control** → "Run Pipeline Now".
3. Watch **Product Factory** for the generated product + real QA results.
4. Go to **Approval Center** and approve the listing draft.
5. Check **Activity Monitor** for the full real-time audit trail.

Or run the automated version of the same thing:
```bash
cd backend && source venv/Scripts/activate && python -m pytest tests/test_digital_product_e2e.py -v -s
```

## Documentation map

| File | Contents |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | System design, data flow, why certain spec items were implemented differently |
| [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) | Phase plan and what each phase delivered |
| [PROGRESS.md](PROGRESS.md) | Feature-by-feature done/not-done checklist against the 26 acceptance criteria |
| [AGENTS.md](AGENTS.md) | Every agent's identity, responsibility, tools, prompt |
| [INTEGRATIONS.md](INTEGRATIONS.md) | How to connect Etsy/Printify/Printful/Shopify/Anthropic/OpenAI |
| [SECURITY.md](SECURITY.md) | Auth, secrets, approval enforcement, known gaps |
| [DEPLOYMENT.md](DEPLOYMENT.md) | Local dev today, path to cloud deployment |
| [TESTING.md](TESTING.md) | What's tested, how to run it, mocked vs live |
| [BUSINESS_OPERATIONS.md](BUSINESS_OPERATIONS.md) | How the owner actually operates this day to day |
