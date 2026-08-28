"""Tests for tools/attribution_engine.py - Marketing Performance AI's reports."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.attribution_engine import build_exec_report, find_roas_drops, week_over_week_roas


def _daily_rows(slug, spend, revenue, days, end="2026-08-27"):
    from datetime import date, timedelta
    end_d = date.fromisoformat(end)
    return [{"asset_slug": slug, "date": (end_d - timedelta(days=i)).isoformat(),
            "spend": spend, "revenue": revenue, "impressions": 1000, "clicks": 20,
            "landing_views": 10, "bookings": 1} for i in range(days)]


def test_week_over_week_roas_splits_trailing_and_prior_seven_days():
    rows = _daily_rows("steady-ad", spend=10, revenue=70, days=30)  # roas 7.0 throughout
    trailing, prior = week_over_week_roas(rows, "steady-ad", "2026-08-27")
    assert trailing == 7.0
    assert prior == 7.0


def test_find_roas_drops_only_flags_past_the_threshold():
    high = _daily_rows("high-drop", spend=10, revenue=70, days=30)  # will be overwritten below
    # trailing 7 days at roas 2, prior days at roas 7
    from datetime import date, timedelta
    end_d = date.fromisoformat("2026-08-27")
    rows = []
    for i in range(30):
        d = (end_d - timedelta(days=i)).isoformat()
        spend, revenue = (10, 20) if i < 7 else (10, 70)  # roas 2.0 vs 7.0
        rows.append({"asset_slug": "high-drop", "date": d, "spend": spend, "revenue": revenue,
                    "impressions": 1000, "clicks": 20, "landing_views": 10, "bookings": 1})
    steady = _daily_rows("steady-ad", spend=10, revenue=70, days=30)
    alerts = find_roas_drops(rows + steady, ["high-drop", "steady-ad"], "2026-08-27", 0.25)
    slugs = {a.asset_slug for a in alerts}
    assert "high-drop" in slugs
    assert "steady-ad" not in slugs


def test_find_roas_drops_ignores_an_ad_with_no_prior_spend():
    rows = _daily_rows("new-ad", spend=10, revenue=20, days=7)  # only exists in trailing week
    alerts = find_roas_drops(rows, ["new-ad"], "2026-08-27", 0.25)
    assert alerts == []


def test_build_exec_report_lists_alerts_and_says_it_does_not_move_budgets():
    from tools.attribution_engine import RoasAlert
    alerts = [RoasAlert("ad-1", 2.0, 7.0, 0.71, "ROAS fell from 7.0x to 2.0x")]
    report = build_exec_report("Hotel Aurora", {"spend": 1000, "revenue": 5000, "bookings": 10,
                                                "roas": 5.0, "ctr_pct": 1.5, "cpc": 0.8},
                               alerts, {"pending_review": 3, "approved": 0}, "2026-08-27")
    assert "Hotel Aurora" in report
    assert "ad-1" in report
    assert "Doesn't move budgets itself" in report
    assert "3 pending review" in report
