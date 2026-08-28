"""Tests for tools/budget_engine.py - the Bard's budget optimizer.

No adapters, no store, no network: every test builds its own tiny ad rows
and checks the engine's arithmetic and thresholds directly.
`tests/test_run_loop.py` covers the end-to-end path on the bundled fixtures.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.budget_engine import analyse_budget, round5

CFG = {
    "rules": {"budget_safety_cap": True},
    "budget": {
        "pause_below_roas_capped": 1.0, "pause_below_roas_uncapped": 1.5,
        "pause_min_spend_30d": 900, "scale_up_roas_min": 7.0,
        "scale_up_daily_budget_max": 200, "scale_factor_capped": 2,
        "scale_factor_uncapped": 3, "hold_roas_above": 20,
        "twin_pairs": [["loser-ad", "winner-ad"]], "twin_roas_gap_min": 2.0,
        "twin_shift_pct": 0.4,
    },
}


def _ad(slug, **over):
    base = {"slug": slug, "name": slug, "platform": "meta", "daily_budget": 100,
           "spend": 1000, "revenue": 3000, "roas": 3.0, "ctr": 1.0}
    base.update(over)
    return base


def test_round5_rounds_to_nearest_five_with_a_five_floor():
    assert round5(0) == 5
    assert round5(2) == 5
    assert round5(12) == 10
    assert round5(13) == 15


def test_pause_fires_on_zero_bookings_and_frees_the_full_budget():
    ads = [_ad("dead-ad", spend=1000, revenue=0, roas=0.0)]
    result = analyse_budget(ads, CFG)
    assert len(result.changes) == 1
    change = result.changes[0]
    assert change.action == "pause"
    assert change.to_daily == 0
    assert "zero attributed bookings" in change.reason
    assert result.summary["freed_monthly"] == 1000


def test_pause_needs_both_low_roas_and_high_spend():
    cheap_failing = _ad("cheap-fail", spend=500, revenue=100, roas=0.2)  # under spend line
    result = analyse_budget([cheap_failing], CFG)
    assert result.changes == []  # a cheap failing test is never auto-paused


def test_pause_below_the_line_branch_names_the_return():
    ads = [_ad("weak-ad", spend=1000, revenue=700, roas=0.7)]
    result = analyse_budget(ads, CFG)
    assert result.changes[0].action == "pause"
    assert "0.7x return" in result.changes[0].reason


def test_twin_pair_rebalances_only_above_the_gap_threshold():
    loser = _ad("loser-ad", spend=1000, revenue=2000, roas=2.0, daily_budget=100, ctr=1.0)
    winner = _ad("winner-ad", spend=1000, revenue=5000, roas=5.0, daily_budget=100, ctr=4.0)
    result = analyse_budget([loser, winner], CFG)
    reallocs = [c for c in result.changes if c.action == "reallocate"]
    assert len(reallocs) == 2
    loser_change = next(c for c in reallocs if c.asset_slug == "loser-ad")
    winner_change = next(c for c in reallocs if c.asset_slug == "winner-ad")
    assert loser_change.to_daily == 100 - round5(100 * 0.4)
    assert winner_change.to_daily == 100 + round5(100 * 0.4)
    assert winner_change.projected_delta_monthly > 0


def test_twin_pair_skipped_when_gap_too_small():
    loser = _ad("loser-ad", spend=1000, revenue=2000, roas=2.0)
    winner = _ad("winner-ad", spend=1000, revenue=2500, roas=2.5)  # gap 0.5 < 2.0
    result = analyse_budget([loser, winner], CFG)
    assert [c for c in result.changes if c.action == "reallocate"] == []


def test_hold_never_scales_a_brand_term_ad():
    ads = [_ad("brand-ad", spend=1000, revenue=59000, roas=59.0, daily_budget=90)]
    result = analyse_budget(ads, CFG)
    assert result.changes[0].action == "hold"
    assert result.changes[0].to_daily == result.changes[0].from_daily
    # hold rows never count toward the actionable proposal total
    assert result.summary["proposals"] == 0


def test_scale_up_only_within_roas_and_budget_ceiling():
    winner = _ad("small-winner", spend=200, revenue=1760, roas=8.8, daily_budget=20)
    too_big = _ad("big-winner", spend=2000, revenue=16000, roas=8.0, daily_budget=250)
    result = analyse_budget([winner, too_big], CFG)
    scaled = [c for c in result.changes if c.action == "scale_up"]
    assert len(scaled) == 1
    assert scaled[0].asset_slug == "small-winner"
    assert scaled[0].to_daily == 40  # 20 * scale_factor_capped(2)


def test_uncapped_safety_off_uses_the_wider_scale_factor_and_pause_line():
    cfg = {**CFG, "rules": {"budget_safety_cap": False}}
    ads = [_ad("winner", spend=200, revenue=1600, roas=8.0, daily_budget=20)]
    result = analyse_budget(ads, cfg)
    assert result.changes[0].to_daily == 60  # 20 * scale_factor_uncapped(3)
    assert result.summary["caps_off"] is True


def test_summary_headline_says_nothing_applies_until_you_say_so():
    ads = [_ad("dead-ad", spend=1000, revenue=0, roas=0.0)]
    result = analyse_budget(ads, CFG)
    assert "Nothing applies until you say so." in result.thinking_log[-1]
