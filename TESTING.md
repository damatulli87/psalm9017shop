# Testing

## What exists today

`backend/tests/test_digital_product_e2e.py` -- the exact **REQUIRED DIGITAL
PRODUCT TEST** from spec section 33. It runs the real pipeline (no mocks
for the pipeline logic itself; the only "mock" involved is the LLM
fallback when no API key is configured, which is labeled as such in the
output) and asserts:
1. Research produced opportunities with evidence.
2. Selection either picked one or validly rejected all.
3. A product specification was created.
4. Real files exist on disk, are non-empty, and are registered as
   `ProductAsset` rows with checksums.
5. All QA checks passed.
6. A marketplace listing draft was created.
7. An approval was queued and is in `pending` status.

This is a **live test, not a mocked one**, for everything except the LLM
text-generation calls (mocked only because no Anthropic/OpenAI key is
configured in this environment) and the Etsy API call (simulated because no
Etsy credentials exist). The Google Trends call is real and hits the
network.

Run it:
```bash
cd backend && source venv/Scripts/activate
python -m pytest tests/test_digital_product_e2e.py -v -s
```
Last verified run: **PASSED** -- generated product #1 ("Printable Chore
Charts - Starter Edition"), a 5-page 612×792pt PDF, a 2000×2000 PNG preview,
and a valid ZIP; all 5 QA checks passed; listing #1 and approval #1 created.
Verified again through the live HTTP API (login → dashboard → approve →
publication stage completed → listing status `published_simulated`).

`backend/tests/test_ultron_oversight.py` -- verifies Psalm 90:17's oversight
layer is a real independent check, not a rubber stamp:
- `test_ultron_reviews_every_run_and_does_not_false_positive` -- runs the
  real pipeline, confirms a `SupervisionReview` is created on every exit
  path, and that a clean run never gets blocked.
- `test_ultron_catches_a_real_inconsistency` -- runs the real pipeline,
  then deliberately deletes one of the product's registered files on disk
  (without touching the DB row) and confirms Psalm 90:17's post-hoc review
  catches the mismatch, returns `verdict="blocked"`, and opens a real
  `operational_concern` Approval -- then restores the file.
- `test_system_health_check_runs_clean` -- runs the system-wide health
  check and confirms it doesn't false-positive against real agent/budget
  state.

Last verified run: all 3 passed, including the deliberate-sabotage case.

## What's NOT built yet

- **Required POD test** (spec section 33): not runnable -- POD production
  agent doesn't exist yet (see PROGRESS.md).
- Unit tests for individual agents/generators in isolation (today they're
  only exercised via the e2e test).
- API/integration tests for every router (auth, approvals, financials,
  settings) beyond the manual `curl` verification done during this build.
- Security tests (auth bypass attempts, policy-engine bypass attempts).
- Database constraint tests.
- End-to-end browser tests (Playwright/Cypress) against the Next.js UI --
  the UI was manually verified to build cleanly (`npm run build`), serve
  all 10 routes with HTTP 200, and render real API data (dashboard summary,
  agent roster, product list) during this build, but there is no automated
  browser test suite yet.

## Adding more tests

`backend/tests/conftest.py` already wires up a bootstrapped DB session
fixture (`_bootstrap_db`, session-scoped, autouse) -- new tests can just
import `app.database.SessionLocal` and go. Keep following the pattern in
`test_digital_product_e2e.py`: assert on real DB rows and real files on
disk, not on mocked return values, wherever the code path isn't already
mock-labeled.
