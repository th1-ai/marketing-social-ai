"""Tests for tools/suggestion_engine.py - the standing suggestion queue."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.suggestion_engine import generate_suggestions

EVENT = {"slug": "regatta", "name": "Regatta week", "start_date": "2026-09-01",
        "end_date": "2026-09-03", "when": "1-3 September"}
CFG = {"rules": {"event_radar": True}, "suggestions": {}, "budget": {"twin_pairs": []}}


def _ad(slug, **over):
    base = {"slug": slug, "kind": "meta_ad", "status": "active", "headline": slug,
           "age_days": 10, "ctr_pct": 1.0, "cvr_pct": 2.0, "roas": 3.0}
    base.update(over)
    return base


def test_event_signal_is_muted_when_event_radar_is_off():
    cfg = {**CFG, "rules": {"event_radar": False}}
    out = generate_suggestions([], [EVENT], [], cfg)
    events = [s for s in out if s.category == "event_signal"]
    assert len(events) == 1
    assert events[0].muted is True


def test_event_signal_prefills_the_studio_brief():
    out = generate_suggestions([], [EVENT], [], CFG)
    event = next(s for s in out if s.category == "event_signal")
    assert event.muted is False
    assert event.prefilled_brief.startswith("Event campaign: ")
    assert "Regatta week" in event.prefilled_brief


def test_headline_test_needs_a_creative_old_enough():
    fresh = _ad("fresh-ad", age_days=10)
    stale = _ad("stale-ad", age_days=90)
    out = generate_suggestions([fresh, stale], [], [], CFG)
    slugs = {s.title for s in out if s.category == "headline_test"}
    assert any("stale-ad" in t for t in slugs)
    assert not any("fresh-ad" in t for t in slugs)


def test_review_ad_needs_the_minimum_mention_count():
    reviews = [{"themes": ["pool"], "body": "great pool"}] * 2  # only 2 mentions
    out = generate_suggestions([], [], reviews, CFG)
    assert [s for s in out if s.category == "review_ad"] == []
    reviews3 = reviews + [{"themes": ["pool"], "body": "loved the pool"}]
    out3 = generate_suggestions([], [], reviews3, CFG)
    assert any(s.category == "review_ad" for s in out3)


def test_landing_page_needs_high_ctr_and_low_conversion():
    working_ad = _ad("working", ctr_pct=2.0, cvr_pct=3.0)  # converts fine
    broken_ad = _ad("broken", ctr_pct=2.0, cvr_pct=0.1)     # clicks but no bookings
    out = generate_suggestions([working_ad, broken_ad], [], [], CFG)
    titles = " ".join(s.title for s in out if s.category == "landing_page")
    assert "broken" in titles
    assert "working" not in titles


def test_cross_property_flags_the_laggard_against_the_leader():
    leader = _ad("aurora-offer", category="offer", property="hotel-aurora", roas=9.0)
    laggard = _ad("marlow-offer", category="offer", property="marlow-house", roas=3.0)
    out = generate_suggestions([leader, laggard], [], [], CFG)
    cross = [s for s in out if s.category == "cross_property"]
    assert len(cross) == 1
    assert "aurora-offer" in cross[0].evidence[0].ref


def test_cross_property_ignores_a_single_property():
    only_one = [_ad("solo-offer", category="offer", property="hotel-aurora", roas=9.0)]
    out = generate_suggestions(only_one, [], [], CFG)
    assert [s for s in out if s.category == "cross_property"] == []


def test_budget_shift_suggestion_needs_the_configured_gap():
    cfg = {**CFG, "budget": {"twin_pairs": [["loser", "winner"]], "twin_roas_gap_min": 2.0}}
    loser = _ad("loser", roas=2.0)
    winner = _ad("winner", roas=2.5)  # gap too small
    out = generate_suggestions([loser, winner], [], [], cfg)
    assert [s for s in out if s.category == "budget_shift"] == []
