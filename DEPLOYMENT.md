# Deployment

## Current state: local dev only

Per the owner's explicit choice for this build, there is no Docker/cloud
config yet -- Docker Desktop is not installed in the dev environment this
was built in, and the owner asked for local-dev-first. Everything below
runs on a single machine.

## Local development

See [README.md](README.md) Quickstart. In short:
```bash
cd backend && python -m venv venv && source venv/Scripts/activate
pip install -r requirements.txt && alembic upgrade head
uvicorn app.main:app --reload --reload-dir app --port 8000
```
`--reload-dir app` matters, not just `--reload` alone: without it, uvicorn
watches the entire `backend/` tree including `venv/` -- real impact found
live (2026-10-14), installing one new pip package (`pip install fonttools`,
for a one-time font-processing step) triggered a reload storm from
hundreds of newly-written files under `venv/Lib/site-packages/`. Scoping
the watch to `app/` avoids that entirely and is also just more correct --
only real source code should trigger a reload.
```bash
cd frontend && npm install && npm run dev
```

## Running continuously without the owner's PC staying on

Not yet deployed anywhere. The path to "operates continuously on cloud
infrastructure" (spec section 32):

1. **Containerize** (not yet done): a `Dockerfile` for `backend/` (Python
   3.13-slim, `pip install -r requirements.txt`, `alembic upgrade head &&
   uvicorn app.main:app --host 0.0.0.0`) and a standard Next.js
   multi-stage `Dockerfile` for `frontend/`. A `docker-compose.yml` adding
   a Postgres service and pointing `DATABASE_URL` at it is straightforward
   given the models are already Postgres-portable -- this is the next
   concrete step once the owner wants to move off SQLite.
2. **Database**: switch `DATABASE_URL` to a managed Postgres instance
   (Railway/Render/RDS/Supabase all work) and run `alembic upgrade head`
   against it once.
3. **Backend host**: any container host that can run a long-lived process
   + a persistent volume for `backend/storage/` (or switch
   `app/integrations/file_storage.py` to S3 first, which is cleaner for
   multi-instance deployments).
4. **Frontend host**: Vercel (zero-config for Next.js) or the same
   container host, with `NEXT_PUBLIC_API_URL` pointed at the deployed
   backend's public URL.
5. **Scheduler**: APScheduler runs in-process with the backend, so as long
   as the backend container stays up, scheduled jobs keep firing. For
   production-grade reliability at scale, replace with a real
   queue/worker (Celery beat + Redis) -- not necessary at this project's
   current size (a handful of jobs/day).
6. **Secrets**: inject via the host's environment-variable mechanism, not
   checked-in `.env` files.

## Backup procedure (manual, today)

- **Database**: `sqlite3 backend/ultron.db ".backup backend/ultron.db.bak"`
  (or, for Postgres, `pg_dump`). Automate via cron/Task Scheduler once
  deployed.
- **Generated product files**: `backend/storage/` is the source of truth
  for every file a customer could receive -- back it up (or migrate to S3,
  which gives you this for free via versioning).

## Recovery procedure (manual, today)

1. Restore the database file/dump.
2. Restore `backend/storage/`.
3. Run `alembic upgrade head` (no-op if already current) and restart the
   backend -- `WorkflowRun`/`Task` rows let you see exactly which workflows
   were mid-flight and whether `resume_after_approval()` needs to be
   called again for any pending approval.

## Production-readiness checklist (spec section 37)

| Requirement | Status |
|---|---|
| Authentication works | ✅ |
| Permission controls work | ✅ (single-owner; no multi-role RBAC) |
| Approval policies enforced | ✅ |
| Database migrations work | ✅ (Alembic, verified) |
| Durable workflows survive restarts | ✅ (DB-backed Task rows; verified the authorization pause/resume path) |
| Product files generated successfully | ✅ (verified: real PDF/XLSX/PNG/ZIP) |
| Quality validation works | ✅ (verified: all QA checks ran and passed on a real product) |
| API integrations verified | ⚠️ Google Trends verified live; Etsy/Printify/Printful/Shopify/Anthropic/OpenAI built but unverified (no credentials available) |
| Secrets protected | ✅ (env-only, gitignored, never sent to frontend) |
| Financial reporting accurate | ✅ (ACTUAL/PROJECTED/UNKNOWN separated; currently $0 ACTUAL, correctly) |
| Budget limits enforced | ✅ |
| Critical tests pass | ✅ (required end-to-end digital product test passes) |
| Backups configured | ❌ manual procedure documented, not automated |
| Monitoring operational | ⚠️ Activity Monitor + AuditEvent log exist; no external alerting/uptime monitoring |

**Conclusion: not yet production-ready for a public deployment** --
specifically missing automated backups, external monitoring/alerting, rate
limiting, and HTTPS. It is ready for continued local-dev iteration and for
connecting real credentials one integration at a time.
