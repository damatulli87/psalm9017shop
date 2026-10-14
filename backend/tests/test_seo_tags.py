"""
Real SEO tag-truncation test -- found live (2026-10-14) during a real
owner-requested pipeline run: the AI is told Etsy tags must be <=20
characters but doesn't reliably respect that, and a plain `tag[:20]`
slice cut tags mid-word, reaching a REAL live Etsy listing with tags like
"chore chart printabl" (should be "printable") and "kids responsibility "
(a dangling trailing space where the word was cut clean off).
"""
from __future__ import annotations

from app.agents.seo import _truncate_tag


def test_short_tags_pass_through_unchanged():
    assert _truncate_tag("chore chart") == "chore chart"
    assert _truncate_tag("  kids chore chart  ") == "kids chore chart"


def test_oversized_tags_truncate_at_a_word_boundary_not_mid_word():
    """The real bug: 'chore chart printable' (22 chars) used to become
    'chore chart printabl' (20 chars, word cut in half) instead of
    dropping back to the last whole word that fits."""
    assert _truncate_tag("chore chart printable") == "chore chart"
    assert _truncate_tag("kids responsibility chart") == "kids responsibility"
    assert _truncate_tag("printable reward system") == "printable reward"
    assert _truncate_tag("daily chore checklist") == "daily chore"


def test_truncated_tags_never_end_with_a_dangling_space():
    for raw in ["chore chart printable", "kids responsibility chart", "printable reward system"]:
        result = _truncate_tag(raw)
        assert result == result.strip() and not result.endswith(" ")


def test_a_single_word_longer_than_the_limit_is_dropped_not_mutilated():
    assert _truncate_tag("supercalifragilisticexpialidocious") is None


def test_exactly_at_the_limit_is_kept_whole():
    tag = "printable task chart"  # exactly 20 chars
    assert len(tag) == 20
    assert _truncate_tag(tag) == tag
