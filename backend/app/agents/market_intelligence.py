"""
Market Intelligence Agent (spec section 5).

Real signal: Google Trends interest-over-time via pytrends (no credentials
needed). Etsy-specific competitive/pricing data requires an approved Etsy
API app; until Etsy credentials are configured that dimension is marked
BLOCKED and contributes zero confidence rather than a guess.

The candidate keyword list is a configurable seed (section 1's own product
category examples) -- not a claim of market insight by itself. All actual
"evidence" comes from the real trend fetch recorded per keyword.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

from app.agents.base import BaseAgent
from app.config import settings
from app.integrations.trends import TrendSignal, fetch_trend_signal
from app.models.models import MarketOpportunity, ResearchSource

# Google Trends rate-limits (HTTP 429) under repeated same-session calls --
# confirmed in practice, not theoretical. Two real mitigations: reuse a
# recent REAL result instead of re-fetching (cache), and space out calls
# that do need a fresh fetch so we don't burst the limiter.
TREND_CACHE_WINDOW = timedelta(hours=20)
TREND_REQUEST_SPACING_SECONDS = 5.0

CANDIDATE_NICHES = [
    # Ordering matters: research_candidates() takes CANDIDATE_NICHES[:limit],
    # and the default scheduled limit is 5 (see scheduler.py). Christian
    # niches are interleaved into the first few slots so they get a real
    # chance at being researched by default, not just on manual runs with a
    # higher niche_limit -- without raising per-run Trends call volume.
    {"keyword": "printable chore chart", "category": "digital", "niche_title": "Printable Chore Charts"},
    {"keyword": "bible verse wall art printable", "category": "digital", "niche_title": "Bible Verse Printable Wall Art"},
    {"keyword": "budget planner printable", "category": "digital", "niche_title": "Printable Budget Planners"},
    {"keyword": "prayer journal printable", "category": "digital", "niche_title": "Prayer Journal Printable"},
    {"keyword": "wedding planning template", "category": "digital", "niche_title": "Wedding Planning Templates"},
    {"keyword": "bible study planner printable", "category": "digital", "niche_title": "Bible Study Planner"},
    {"keyword": "small business invoice template", "category": "digital", "niche_title": "Small Business Invoice Templates"},
    {"keyword": "bible verse coffee mug", "category": "pod", "niche_title": "Scripture Verse Coffee Mugs"},
    {"keyword": "printable daily planner", "category": "digital", "niche_title": "Printable Daily Planners"},
    {"keyword": "christian faith t shirt", "category": "pod", "niche_title": "Faith-Based Graphic T-Shirts"},
    {"keyword": "digital journal template", "category": "digital", "niche_title": "Digital Journal Templates"},
    {"keyword": "sunday school worksheets printable", "category": "digital", "niche_title": "Sunday School Activity Worksheets"},
    {"keyword": "funny cat t shirt", "category": "pod", "niche_title": "Funny Cat-Lover T-Shirts"},
    {"keyword": "motivational quote mug", "category": "pod", "niche_title": "Motivational Quote Mugs"},
    {"keyword": "teacher appreciation gift", "category": "pod", "niche_title": "Teacher Appreciation POD Gifts"},
    {"keyword": "home office productivity planner", "category": "digital", "niche_title": "Home Office Productivity Planners"},
]


class MarketIntelligenceAgent(BaseAgent):
    key = "market_intelligence"

    def _get_cached_trend(self, keyword: str) -> ResearchSource | None:
        """A recent REAL Trends result for this exact keyword, if one exists
        within the cache window -- reused instead of a fresh network call.
        Never caches a failed/unavailable result, since that would just
        replay the rate-limit error instead of retrying it."""
        cutoff = datetime.now(timezone.utc) - TREND_CACHE_WINDOW
        return (
            self.db.query(ResearchSource)
            .filter(
                ResearchSource.name == f"Google Trends: {keyword}",
                ResearchSource.source_type == "google_trends",
                ResearchSource.is_real_data.is_(True),
                ResearchSource.retrieved_at >= cutoff,
            )
            .order_by(ResearchSource.retrieved_at.desc())
            .first()
        )

    def research_candidates(self, workflow_run_id: int | None = None, limit: int = 5) -> list[MarketOpportunity]:
        opportunities: list[MarketOpportunity] = []
        made_a_real_call = False

        for candidate in CANDIDATE_NICHES[:limit]:
            cached = self._get_cached_trend(candidate["keyword"])
            if cached:
                raw = cached.raw_data
                signal = TrendSignal(
                    keyword=candidate["keyword"],
                    is_real_data=True,
                    average_interest=raw.get("average_interest"),
                    trend_direction=raw.get("trend_direction"),
                    error=None,
                )
                source = ResearchSource(
                    name=cached.name,
                    source_type="google_trends_cached",
                    is_real_data=True,
                    url=cached.url,
                    raw_data={**raw, "cached_from_source_id": cached.id, "cached_from_retrieved_at": cached.retrieved_at.isoformat()},
                )
                self.db.add(source)
                self.db.commit()
                self.db.refresh(source)
            else:
                if made_a_real_call:
                    time.sleep(TREND_REQUEST_SPACING_SECONDS)
                signal = fetch_trend_signal(candidate["keyword"])
                made_a_real_call = True

                source = ResearchSource(
                    name=f"Google Trends: {candidate['keyword']}",
                    source_type="google_trends" if signal.is_real_data else "google_trends_unavailable",
                    is_real_data=signal.is_real_data,
                    url=f"https://trends.google.com/trends/explore?q={candidate['keyword'].replace(' ', '%20')}",
                    raw_data={
                        "average_interest": signal.average_interest,
                        "trend_direction": signal.trend_direction,
                        "series_points": len(signal.raw_series),
                        "error": signal.error,
                    },
                )
                self.db.add(source)
                self.db.commit()
                self.db.refresh(source)

            etsy_note = (
                "Etsy competitive/pricing data BLOCKED -- no Etsy API credentials configured. "
                "Contributes 0 to differentiation/competition confidence until connected."
                if not settings.etsy_configured
                else "Etsy competitive data pending implementation of authenticated search calls."
            )

            evidence = {
                "trend_source_id": source.id,
                "is_real_data": signal.is_real_data,
                "average_interest_0_100": signal.average_interest,
                "trend_direction": signal.trend_direction,
                "trend_error": signal.error,
                "etsy_competition_data": etsy_note,
            }

            opp = MarketOpportunity(
                workflow_run_id=workflow_run_id,
                niche_title=candidate["niche_title"],
                category=candidate["category"],
                description=f"Candidate niche seeded from configured category list: {candidate['keyword']}.",
                evidence_summary=evidence,
                source_ids=[source.id],
            )
            self.db.add(opp)
            self.db.commit()
            self.db.refresh(opp)
            opportunities.append(opp)

            self.log(
                "research_completed",
                f"Researched '{candidate['niche_title']}' "
                f"({'REAL' if signal.is_real_data else 'UNAVAILABLE'} trend data)",
                evidence,
            )

        return opportunities
