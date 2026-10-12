"""
Real external research signal: Google Trends via pytrends (no API key
required -- it calls the same public endpoints the Trends website uses).

This is the one "real data" source Psalm 90:17 Commerce has out of the box
without any owner-supplied credentials. Etsy's own marketplace-search data
requires an authenticated, approved Etsy API app and is intentionally left
BLOCKED/awaiting-configuration (see app/integrations/etsy.py) rather than
scraped, per spec section 5 ("do not violate marketplace terms or
circumvent access restrictions").

If the network call fails for any reason (offline sandbox, rate limiting,
pytrends/Google API change), we return is_real_data=False with the error
recorded -- we never substitute a fabricated number silently.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TrendSignal:
    keyword: str
    is_real_data: bool
    average_interest: float | None = None  # 0-100 Google Trends relative interest
    trend_direction: str | None = None  # rising/falling/flat/unknown
    raw_series: list = field(default_factory=list)
    error: str | None = None


def fetch_trend_signal(keyword: str, timeframe: str = "today 12-m") -> TrendSignal:
    try:
        from pytrends.request import TrendReq

        pytrends = TrendReq(hl="en-US", tz=360, timeout=(5, 10))
        pytrends.build_payload([keyword], timeframe=timeframe, geo="US")
        df = pytrends.interest_over_time()
        if df is None or df.empty:
            return TrendSignal(keyword, is_real_data=False, error="No data returned for keyword.")

        series = df[keyword].tolist()
        avg = sum(series) / len(series) if series else 0.0
        half = max(1, len(series) // 2)
        first_half_avg = sum(series[:half]) / half
        second_half_avg = sum(series[half:]) / max(1, len(series) - half)
        if second_half_avg > first_half_avg * 1.1:
            direction = "rising"
        elif second_half_avg < first_half_avg * 0.9:
            direction = "falling"
        else:
            direction = "flat"

        return TrendSignal(
            keyword=keyword,
            is_real_data=True,
            average_interest=round(avg, 2),
            trend_direction=direction,
            raw_series=series,
        )
    except Exception as exc:  # network unavailable, rate-limited, library/API change, etc.
        return TrendSignal(keyword, is_real_data=False, error=f"{type(exc).__name__}: {exc}")
