# Business Operations (Owner's Guide)

This describes how you, the owner, actually operate Psalm 90:17 Commerce today
-- not the eventual vision, the current reality.

## Right now, with zero credentials configured

The system will research niches (real Google Trends signal), pick the best
one (or honestly reject all of them), generate a real digital product
file, QA-validate it, and prepare an Etsy listing draft -- then stop and
wait for you in the **Approval Center**. Nothing is published anywhere
real, no money is spent, and the Financial Command Center will correctly
show $0.00 ACTUAL revenue and $0.00 ACTUAL expenses, because that's the
truth: nothing real has happened on a marketplace yet.

Your weekly loop today:
1. Open the command center, log in.
2. **Mission Control** → Run Pipeline Now (or wait for the Monday 8am
   scheduled job, already enabled).
3. **Product Factory** → inspect the generated product and download the
   actual files to sanity-check them yourself.
4. **Approval Center** → approve or reject the listing draft.
5. **Activity Monitor** → skim for anything that errored.

That's roughly the "1-3 hours/week" target from the spec, already
achievable for the discovery→draft portion of the loop.

## Turning this into a real, selling business

In order, each step unlocks more real automation:

1. **Connect Etsy** (see INTEGRATIONS.md). Once `ETSY_API_KEY`,
   `ETSY_API_SECRET`, `ETSY_SHOP_ID` are set and the OAuth token flow is
   completed, listing drafts stop being simulated and the Approval Center's
   "Approve" button results in a real Etsy draft listing. You still decide
   when a listing goes fully live on Etsy itself (Etsy drafts require a
   separate "publish" action in Etsy's own UI by design, as an extra safety
   margin).
2. **Add an Anthropic or OpenAI key** so product narratives, SEO copy, and
   design briefs come from a real model instead of the structural mock
   fallback. Cost is tracked automatically and capped at
   `MONTHLY_AI_BUDGET_USD` ($150 default).
3. **Make your first real sale.** The Financial Controller will then have
   a real `Transaction` row to report on, and ACTUAL figures in the
   Financial Command Center stop being zero.
4. **POD and Shopify** are not built yet (see PROGRESS.md) -- they're the
   next construction phases, deliberately sequenced after the digital
   pipeline proved out, per the spec's own Day 1-30 / 31-60 plan.

## What Psalm 90:17 will never do without asking you

- Spend money on advertising (`advertising_enabled=false` by default,
  enforced in the policy engine, not just the UI).
- Publish anything to a real marketplace (`SUPERVISED` mode requires your
  approval for every `publish_listing` action; this is hard-coded, not a
  prompt instruction).
- Exceed the `$1,000` startup budget ceiling or the `$150/month` AI budget
  -- the policy engine blocks the action before it runs, not after.
- Process a refund, open a new subscription, or touch a financial account
  without your explicit approval.

## Honest limitations to plan around

- There is exactly one curated candidate-niche list today (10 seed
  keywords across digital + POD categories in
  `app/agents/market_intelligence.py`) -- it is not yet pulling an
  open-ended stream of niche ideas. Expanding that list, or having an LLM
  propose new candidate keywords for Market Intelligence to check against
  Trends, is a natural next step once you're ready to go deeper than the
  first 10.
- There is no real competitive/pricing data from Etsy itself yet (requires
  the Etsy connection in step 1 above) -- the opportunity scorer is
  explicit about this gap (`"etsy_competition_data": "...BLOCKED..."`)
  rather than guessing.
- Self-improvement (spec section 19) hasn't started -- it needs multiple
  weeks of real sales data to learn from, which doesn't exist yet.
