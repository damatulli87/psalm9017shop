# Security

## Implemented

- **Owner authentication**: single-owner JWT auth (`backend/app/auth/`),
  bcrypt-hashed password, 12-hour token expiry. All API routes except
  `/health` and `/auth/login` require a valid bearer token
  (`get_current_user` dependency on every router).
- **Secrets never reach the frontend**: all provider API keys live in
  `backend/.env` (gitignored), read only by `app/config.py` on the backend.
  The frontend only ever holds the owner's own JWT in `localStorage`.
- **Independent policy enforcement**: `app/policy/engine.py` contains no AI
  calls and cannot be influenced by agent/LLM output. Publishing,
  advertising spend, refunds above limit, subscriptions, code deployment,
  permission changes, and destructive operations are hard-coded into
  `ALWAYS_REQUIRES_APPROVAL` and enforced regardless of what any agent
  "decides."
- **Budget enforcement**: `budget_check()` reads real `Expense` rows and
  blocks any action whose estimated cost would exceed the per-action,
  monthly-AI, or startup-ceiling caps in `app/config.py` -- before the
  action executes, not after.
- **Audit logging**: every agent action, policy block, and approval
  decision is written to `AuditEvent` (see `/activity`), independent of
  whether the action succeeded.
- **No raw static secrets in the DB**: `IntegrationCredential` rows store
  connection *status* only, never an API key/secret. OAuth tokens are a
  different case -- they're obtained dynamically and must be persisted
  somewhere the app can use and refresh them, so `OAuthToken` rows store
  them encrypted at rest (`app/integrations/crypto.py`, Fernet, key derived
  from `SECRET_KEY`) and they're never returned by any API response.
- **Customer data minimization**: `Customer.email_hash` stores a hash, not
  a raw email (spec section 24, Customer Memory scope).

## Known gap: the Etsy OAuth connect endpoint is unauthenticated

`GET /integrations/etsy/connect` is deliberately not behind the owner JWT
check, because it's a full-page browser redirect (to Etsy's consent screen
and back) that can't carry a bearer header, and this app has no
session-cookie infrastructure. Etsy's own login/consent screen is the real
gate on who can complete the flow -- an attacker hitting this endpoint
without also controlling the Etsy account's login can't actually link
anything. Acceptable for local-only single-owner use; before exposing this
backend to the internet, add session-cookie-based protection on this
specific route (the rest of the API is unaffected -- everything else still
requires the bearer token).

## Explicitly NOT implemented yet (do not deploy publicly without these)

- **Rate limiting** on the API is not implemented. Add a reverse-proxy
  layer (e.g. nginx/Caddy with rate limiting, or `slowapi`) before any
  public deployment.
- **Prompt-injection defenses**: the Executive AI Chat
  (`app/routers/chat.py`) deliberately uses keyword matching instead of
  free-form LLM tool-calling specifically to avoid this risk class for now;
  there is no sandboxing layer because there is no agent yet that executes
  arbitrary tool calls from untrusted text (customer messages, scraped
  pages). Build that sandboxing *before* wiring the Customer Service Agent
  to real inbound messages.
- **HTTPS/TLS** is not configured -- this runs over plain HTTP in local
  dev. A real deployment needs a TLS-terminating proxy.
- **Secret manager integration** (e.g. AWS Secrets Manager/Vault) -- `.env`
  files are adequate for a single-owner side project but not for a team or
  regulated deployment.
- **Emergency stop / workflow cancellation**: there is no kill-switch
  endpoint yet. The scheduler's `enabled` flag on each `ScheduledJob` can
  disable future runs, and `advertising_enabled=false` blocks all paid
  spend by default, but a running workflow cannot currently be cancelled
  mid-execution. Add a `WorkflowRun.status = "cancelling"` check inside
  each stage of `workflow_engine.py` before relying on this for anything
  irreversible.
- **Backup/recovery automation**: not implemented. See DEPLOYMENT.md for
  the manual procedure in the meantime.
- **Role-based permissions beyond "owner"**: only one role exists today.

## Dev-mode defaults you must change before any real deployment

- `SECRET_KEY` in `app/config.py` is an insecure placeholder.
- The default owner password is `ultron-dev-only` -- rotate it via
  `POST /auth/change-password` immediately.
