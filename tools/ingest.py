"""tools/ingest.py - load the signals no core adapter exposes.

Ad performance, the brand kit, reviews and local events are not things a
PMS or an email inbox gives you (docs/how-it-works.md "Design decisions"
#1). Each loader checks `data/imports/<name>.json` first (your own export,
or a script you point at a real source), then falls back to the matching
`fixtures/` file so `make demo` and the tests always have something to read.

Every loader returns plain dicts/lists - no dataclasses here, those live in
the engine modules that consume this data.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load(import_name: str, fixture_rel: str) -> Any:
    imported = REPO_ROOT / "data" / "imports" / import_name
    if imported.exists():
        return json.loads(imported.read_text(encoding="utf-8"))
    fixture = REPO_ROOT / fixture_rel
    if fixture.exists():
        return json.loads(fixture.read_text(encoding="utf-8"))
    return []


def load_ad_performance() -> list[dict]:
    """Daily rows: asset_slug, date, impressions, clicks, landing_views,
    bookings, spend, revenue. See fixtures/inbound/ad_performance.json."""
    return _load("ad_performance.json", "fixtures/inbound/ad_performance.json")


def load_marketing_assets() -> list[dict]:
    """Ad/content rows: slug, kind, name, headline, status, daily_budget..."""
    return _load("marketing_assets.json", "fixtures/hotel/marketing_assets.json")


def load_content_assets() -> list[dict]:
    """The brand kit: photos, logos, colours, fonts, voice docs."""
    return _load("content_assets.json", "fixtures/hotel/content_assets.json")


def load_content_performance() -> list[dict]:
    """Monthly blog/newsletter rows: asset_slug, month, views, opens..."""
    return _load("content_performance.json", "fixtures/inbound/content_performance.json")


def load_reviews() -> list[dict]:
    """Guest reviews, for review-quote suggestions and the copilot's search."""
    return _load("reviews.json", "fixtures/inbound/reviews.json")


def load_events() -> list[dict]:
    """Local events/signals for the event-radar suggestion category."""
    return _load("events.json", "fixtures/inbound/events.json")


def sources_used() -> dict[str, str]:
    """Which signal came from a real import vs. the demo fixtures - for doctor."""
    out = {}
    pairs = [
        ("ad_performance", "ad_performance.json"), ("content_assets", "content_assets.json"),
        ("reviews", "reviews.json"), ("events", "events.json"),
    ]
    for name, filename in pairs:
        imported = REPO_ROOT / "data" / "imports" / filename
        out[name] = f"data/imports/{filename}" if imported.exists() else "demo fixtures (none imported)"
    return out


def aggregate_30d(rows: list[dict], asset_slug: str, *, days: int = 30,
                   as_of: str | None = None) -> dict:
    """Sum one asset's daily rows over the trailing window and derive rates.

    Mirrors the source's `aggregateRows`: ctr_pct/roas/cpc rounded to 2dp.
    Rows outside the window (by ISO date string comparison) are ignored.
    """
    from datetime import date, timedelta
    end = date.fromisoformat(as_of) if as_of else date.today()
    start = (end - timedelta(days=days)).isoformat()
    end_s = end.isoformat()
    matched = [r for r in rows if r.get("asset_slug") == asset_slug and start <= r["date"] <= end_s]
    spend = round(sum(r.get("spend", 0) for r in matched), 2)
    revenue = round(sum(r.get("revenue", 0) for r in matched), 2)
    impressions = sum(r.get("impressions", 0) for r in matched)
    clicks = sum(r.get("clicks", 0) for r in matched)
    landing_views = sum(r.get("landing_views", 0) for r in matched)
    bookings = sum(r.get("bookings", 0) for r in matched)
    return {
        "asset_slug": asset_slug, "spend": spend, "revenue": revenue,
        "impressions": impressions, "clicks": clicks, "landing_views": landing_views,
        "bookings": bookings,
        "roas": round(revenue / spend, 2) if spend else 0.0,
        "ctr_pct": round(100 * clicks / impressions, 2) if impressions else 0.0,
        "cpc": round(spend / clicks, 2) if clicks else 0.0,
        "cpm": round(1000 * spend / impressions, 2) if impressions else 0.0,
        "cvr_pct": round(100 * bookings / clicks, 2) if clicks else 0.0,
    }
