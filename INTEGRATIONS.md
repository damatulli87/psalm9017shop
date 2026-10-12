# Integrations

Every integration below is built against the provider's real/public API
surface. None are faked -- when credentials are absent, the code says so
explicitly in logs and API responses (`is_simulated` / `is_mock` /
`is_real_data` fields) rather than pretending to be connected.

## Google Trends (active now, no credentials needed)

`backend/app/integrations/trends.py` uses `pytrends` against the public
endpoints the Trends website itself uses -- no API key, no ToS
circumvention. Verified working in this environment:
```
fetch_trend_signal("budget planner printable")
-> is_real_data=True, average_interest=17.28, trend_direction="rising"
```
If the network call fails for any reason, `is_real_data=False` and the
error is recorded -- the opportunity scorer then penalizes confidence
instead of guessing.

## Etsy Open API v3

Fully wired end to end: OAuth2/PKCE authorize flow, callback, encrypted
token storage with transparent refresh, and the real
`POST /shops/{shop_id}/listings` draft-creation call. To connect:

1. Make sure you have an Etsy shop (shop ID is visible in Shop Manager ->
   Settings -> Options, or in your shop's URL).
2. Register an app at https://www.etsy.com/developers/your-apps. Set its
   **callback/redirect URI** to exactly `http://localhost:8000/integrations/etsy/callback`
   (must match `ETSY_OAUTH_REDIRECT_URI` below) -- note Etsy requires this
   to be HTTPS for apps that aren't in sandbox/dev mode; for local
   development with a dev-mode app, `http://localhost` is normally
   permitted. If Etsy rejects a plain `http://localhost` redirect for your
   app, use a tunnel (e.g. `ngrok http 8000`) and set
   `ETSY_OAUTH_REDIRECT_URI` to the tunnel's HTTPS URL instead.
3. Copy the app's **Keystring** (API key) and **Shared Secret** into
   `backend/.env`:
   ```
   ETSY_API_KEY=your_keystring
   ETSY_API_SECRET=your_shared_secret
   ETSY_SHOP_ID=your_numeric_shop_id
   ETSY_OAUTH_REDIRECT_URI=http://localhost:8000/integrations/etsy/callback
   ```
4. Restart the backend (`uvicorn app.main:app --reload`).
5. In the command center, go to **Marketplace Center** -- a "Connect Etsy"
   button now appears next to Etsy. Click it, approve the consent screen
   on Etsy's site, and you'll land back on Marketplace Center with
   "Connected."
6. From that point on, every listing the pipeline prepares is sent to Etsy
   for real (still created in **draft** state -- Etsy itself requires a
   separate, deliberate action in its own UI to actually publish a draft
   listing live, which is an extra safety margin on top of this app's own
   approval gate).

Token storage: `backend/app/models/models.py::OAuthToken`, encrypted at
rest with a key derived from `SECRET_KEY` (`app/integrations/crypto.py`).
Expired access tokens refresh automatically
(`app/integrations/oauth_store.py::get_valid_etsy_token`); if the refresh
token itself is no longer valid, listings fall back to simulated mode and
the Marketplace Center will show "Configured (OAuth not completed)" again
-- reconnect from there.

## Printify / Printful

Not implemented. `app/config.py` already has `PRINTIFY_API_TOKEN` /
`PRINTFUL_API_TOKEN` settings and `printify_configured` /
`printful_configured` properties so the integration-status UI and policy
engine are ready for them, but there is no adapter module yet -- this is
Phase 5 work (POD production), intentionally deferred until the digital
pipeline is proven (which it now is).

## Shopify

Not implemented, and per spec section 13 it should not activate itself
regardless -- `shopify_configured` exists for status display only.

## Anthropic / OpenAI

`backend/app/integrations/ai_providers.py`. Set `ANTHROPIC_API_KEY` and/or
`OPENAI_API_KEY` in `backend/.env`; real calls activate immediately with no
other code changes, and cost is tracked per-call. With neither set, every
agent that would call an LLM gets a structurally valid `MOCK_LLM` response
instead (clearly labeled `"mock": true` in the output) so the pipeline
remains testable end-to-end.

## Object storage / email notifications

Not implemented. Product files are stored on local disk under
`backend/storage/products/<id>/` (see `app/integrations/file_storage.py`);
swapping in S3-compatible storage only requires changing that one module.
Email notification settings exist in config but no sender is wired yet.
