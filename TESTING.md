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

`backend/tests/test_order_fulfillment.py` -- added in direct response to the
owner's directive that a buyer must never fail to receive what they paid
for. Runs against the real test DB and the real policy/approval engine;
only the actual network boundary is mocked (a real Etsy OAuth token and a
real Printify production order can't be created in a test run):
- `test_digital_order_with_real_file_is_marked_delivered` /
  `_with_no_file_raises_concern_not_false_success` -- the real live bug
  found this session (a digital Etsy listing can exist without ever having
  had its file uploaded) must never be reported as delivered; the agent
  verifies the real listing's `listing_type`/`file_data` before trusting
  `product_type == "digital"`.
- `test_pod_order_requires_real_approval_before_any_printify_call` /
  `_submits_to_printify_only_after_owner_approves` /
  `_rejected_by_owner_never_reaches_printify` -- confirms `submit_order()`
  is physically unreachable until a real `pod_paid_production_order`
  approval is granted (asserts by raising if called early), and that a real
  approval correctly triggers it via `decide_approval()` →
  `resume_after_approval()`, with the real buyer address correctly mapped.
- `test_check_for_new_orders_is_idempotent_on_repeat_calls` -- a repeated
  scheduler run must never double-process the same real Etsy receipt into
  two orders/sales.

Last verified run: all 8 passed (6 above plus
`test_pod_order_ships_the_real_purchased_variant_when_mapped` and
`_falls_back_and_flags_concern_when_product_id_unmapped`, added alongside
the real size/color variation fix below). **Not covered by any test,
deliberately:** a real end-to-end call to `printify.submit_order()`
against the live API -- doing so would place a real, costly production
order and attempt a real shipment with no real buyer behind it.

`backend/tests/test_etsy_variations.py` -- real Etsy listing size/color
variation tests, added in direct response to "correct the size and color
issue." `printify.get_variants()` is monkeypatched to the exact real
response shape captured live (2026-10-14), not a simplified stand-in; the
Etsy property/value ids used (color property 200, shirt-size property
62809790533) are the real ones confirmed live via
`get_taxonomy_properties()`:
- `test_tshirt_builds_real_color_and_normalized_size_for_every_variant` --
  confirms Printify's real "2XL" correctly normalizes to Etsy's real "2X"
  value (a plain string match would silently match nothing), and every
  offering carries the real `readiness_state_id` the live API requires.
- `test_cap_colors_with_no_exact_etsy_match_fall_back_to_nearest_generic_bucket`
  -- Khaki/Dark Green/Dark Navy have no exact match in Etsy's 19-color
  generic list; confirms they map to the nearest real bucket (Beige/Green/
  Blue) rather than being dropped.
- `test_notebook_color_collision_falls_back_to_real_literal_names` -- the
  real bug this caught before it ever reached a live listing: the
  notebook's real Blue/Navy/Turquoise would all collapse into Etsy's
  single generic "Blue," making 3 of 8 variants indistinguishable.
  Confirms the fallback to real literal color names as free text.
- `test_single_real_variant_product_returns_none` -- mug/necklace/tumbler
  have one real variant; confirms no inventory call is attempted.
- `test_sku_on_property_reflects_actual_properties_used` /
  `test_normalize_shirt_size_handles_plain_and_printify_style_names` --
  the two undocumented real API requirements found live (every offering
  needs `readiness_state_id`; `sku_on_property` is required once products
  have distinct skus) and the size-name normalization logic.

Last verified run: all 6 passed. The real `set_listing_inventory()` PUT
call itself was verified live against a real test draft listing
(external_listing_id 4595180993, t-shirt taxonomy) -- all 10 variants
landed with correct real product_ids, confirmed via a fresh
`get_listing_inventory()` read-back. That real test listing has since
disappeared on its own (checked after the fact -- Etsy appears to expire
unpublished draft listings after a while, same as 4 of the 5 earlier test
listings this session), so no manual cleanup was needed for this one.

`backend/tests/test_chore_chart_generator.py` /
`test_digital_content_plan.py` -- real digital-product content-quality
tests, added in direct response to "the chore chart we are creating is
super super basic compared to ones selling for $5 on etsy." Both actually
render the real PDF and inspect it (page count, dimensions, real AcroForm
field counts/types), not just confirm `generate_*()` runs without raising:
- Chore chart: confirms the real 5-page bundle (cover, instructions,
  weekly, monthly, reward/allowance) and its 128 real fillable fields (124
  checkboxes + 4 text fields).
- Content plan: confirms the real checklist/table/tracker renderer
  produces real fillable fields, that a wide (6-column) table never
  overlaps column headers (a real bug found by actually rendering and
  looking at a real generated wedding-planning PDF, not just generating
  it -- fixed with real `stringWidth`-based truncation instead of a flat
  character count), and that the content-plan validator accepts real-shaped
  AI output while rejecting malformed shapes (including a real wrong-shape
  LLM response actually observed live: `{"section", "description",
  "subsections"}` instead of the requested schema).

Last verified run: all 9 passed (3 + 6).

**Real end-to-end pipeline verification (2026-10-14):** the owner asked to
actually run a real pipeline and look at what it produces. First run
failed at `listing_creation` -- investigation found the real cause wasn't
a code bug at all: the running `uvicorn` process had been up since before
all of this session's fixes and was never restarted (started without
`--reload`, deviating from the documented dev command in DEPLOYMENT.md),
so it was serving stale code -- confirmed by the generated chore-chart PDF
having only the old 2 pages / 0 form fields. Restarted the server (this
time with `--reload`, matching DEPLOYMENT.md, so this can't silently
recur) and re-ran: real research (8 real niches, Google Trends real for
most, a couple rate-limited/"UNAVAILABLE" as already known), real
differentiated opportunity scoring (0.72 selected over 0.39-0.52
rejected), a real 5-page fillable chore-chart bundle generated, a real
AI-generated listing photo, and a real Etsy listing successfully created
end-to-end (external_listing_id 4595212237, verified by fetching the
listing and its uploaded photo directly from Etsy's CDN) -- now sitting
in the real approval queue (SUPERVISED mode) same as every other listing.

That real run also surfaced a second, genuine code bug:
`backend/tests/test_seo_tags.py` -- the AI is told Etsy tags must be <=20
characters but doesn't reliably respect that, and the old `tag[:20]` slice
cut tags mid-word -- reached the real live listing above with tags like
"chore chart printabl" (should be "printable") and "kids responsibility "
(a dangling trailing space where the word was cut clean off). Fixed with
`_truncate_tag()` (word-boundary truncation, or drop the tag entirely if
even the first word doesn't fit), verified by regenerating real SEO copy
for the real product and confirming all 13 tags came back clean.
`backend/tests/test_listing_hygiene.py` covers the companion fix:
`UltronSupervisorAgent.verify_listing_hygiene()` gained a new
deterministic check (`listing_hygiene_no_mangled_tags`) for a tag that
doesn't equal its own `.strip()`, so a regression of this exact failure
mode would be caught automatically on the next run.

Last verified run: all 7 passed (5 + 2). Full suite: 34/34.

## What's NOT built yet

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
