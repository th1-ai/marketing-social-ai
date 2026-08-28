"""tools/suggestion_engine.py - generate the Bard's standing suggestion queue.

The source demo seeds this queue by hand and lets the copilot add to it
(specs/marketing-social-ai.md "Open questions" #1: "there is no suggestion
engine"). This module is the real generator: every suggestion is derived
from a number in the ingested data, with the evidence attached, so a human
can see exactly why it exists - never invented, never random.

Pure functions: takes the ingested rows + config, returns Suggestion objects.
`tools/run.py` is the only place that writes them to the store.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

CATEGORY_LABELS = {
    "headline_test": "Headline test", "review_ad": "Review ad",
    "budget_shift": "Budget shift", "new_creative": "New creative",
    "cross_property": "Cross-property", "landing_page": "Landing page",
    "event_signal": "Event radar",
}


@dataclass
class Evidence:
    type: str  # asset | review_theme | metric | event
    ref: str
    label: str


@dataclass
class Suggestion:
    slug: str
    category: str
    title: str
    rationale: str
    impact: str
    evidence: list[Evidence] = field(default_factory=list)
    muted: bool = False
    prefilled_brief: str = ""


def _event_suggestions(events: list[dict], ads: list[dict], radar_on: bool) -> list[Suggestion]:
    out = []
    for ev in events:
        title = f"{ev['name']}, {ev.get('when', 'soon')} - target attendees before demand peaks"
        rationale = ev.get("rationale", f"{ev['name']} covers {ev.get('start_date', '?')} to "
                          f"{ev.get('end_date', '?')} - build the offer before the search "
                          f"volume does.")
        out.append(Suggestion(
            slug=f"sg-event-{ev['slug']}", category="event_signal", title=title,
            rationale=rationale, impact=ev.get("impact", "Uplift not yet estimated"),
            evidence=[Evidence("event", ev["slug"], ev["name"])],
            muted=not radar_on,
            prefilled_brief=f"Event campaign: {title}. {rationale}",
        ))
    return out


def _headline_test_suggestions(ads: list[dict], min_age_days: int = 60) -> list[Suggestion]:
    out = []
    for a in ads:
        if a.get("kind") not in ("meta_ad", "google_ad") or a.get("status") != "active":
            continue
        if a.get("age_days", 0) < min_age_days:
            continue
        out.append(Suggestion(
            slug=f"sg-headline-{a['slug']}", category="headline_test",
            title=f"Test a new headline on \"{a.get('headline', a['slug'])}\"",
            rationale=f"This creative has run unchanged for {a['age_days']} days - a fresh "
                     f"headline is the cheapest test available before it fatigues further.",
            impact="Cheapest test in the queue",
            evidence=[Evidence("asset", a["slug"], a.get("headline", a["slug"]))],
        ))
    return out


def _review_ad_suggestions(reviews: list[dict], min_mentions: int = 3) -> list[Suggestion]:
    from collections import Counter
    counter: Counter[str] = Counter()
    quotes: dict[str, str] = {}
    for r in reviews:
        for theme in r.get("themes", []):
            counter[theme] += 1
            quotes.setdefault(theme, r.get("body", "")[:120])
    out = []
    for theme, count in counter.items():
        if count < min_mentions:
            continue
        out.append(Suggestion(
            slug=f"sg-review-{theme}", category="review_ad",
            title=f"Turn \"{theme}\" into a review-quote ad",
            rationale=f"{count} recent reviews mention {theme} - guests are already saying "
                     f"it, an ad just has to repeat them.",
            impact=f"{count} reviews to draw from",
            evidence=[Evidence("review_theme", theme, quotes[theme])],
        ))
    return out


def _budget_shift_suggestions(ads: list[dict], twin_pairs: list[list[str]],
                              gap_min: float) -> list[Suggestion]:
    by_slug = {a["slug"]: a for a in ads}
    out = []
    for loser_slug, winner_slug in twin_pairs:
        loser, winner = by_slug.get(loser_slug), by_slug.get(winner_slug)
        if not loser or not winner or winner["roas"] - loser["roas"] < gap_min:
            continue
        out.append(Suggestion(
            slug=f"sg-budgetshift-{loser_slug}-{winner_slug}", category="budget_shift",
            title=f"Shift budget from \"{loser_slug}\" to \"{winner_slug}\"",
            rationale=f"{winner_slug} returns {winner['roas']:.1f}x against {loser_slug}'s "
                     f"{loser['roas']:.1f}x - the budget desk can move this inside the "
                     f"safety cap.",
            impact=f"+{winner['roas'] - loser['roas']:.1f}x return gap",
            evidence=[Evidence("metric", winner_slug, f"{winner_slug} — ROAS "
                              f"{winner['roas']:.1f}")],
        ))
    return out


def _landing_page_suggestions(ads: list[dict], ctr_min: float = 1.5,
                              cvr_max: float = 0.5) -> list[Suggestion]:
    out = []
    for a in ads:
        if a.get("ctr_pct", 0) >= ctr_min and a.get("cvr_pct", 100) < cvr_max:
            out.append(Suggestion(
                slug=f"sg-landing-{a['slug']}", category="landing_page",
                title=f"Check the landing page behind \"{a.get('headline', a['slug'])}\"",
                rationale=f"{a['ctr_pct']:.1f}% CTR but only {a['cvr_pct']:.1f}% of clicks "
                         f"convert - the ad is working, the page after it may not be.",
                impact="Click-to-book gap",
                evidence=[Evidence("asset", a["slug"], a.get("headline", a["slug"]))],
            ))
    return out


def _cross_property_suggestions(ads: list[dict]) -> list[Suggestion]:
    """Same category, different properties: flag the laggard against the leader."""
    by_category: dict[str, list[dict]] = {}
    for a in ads:
        if a.get("status") != "active" or not a.get("property"):
            continue
        by_category.setdefault(a.get("category", a.get("kind", "")), []).append(a)
    out = []
    for category, rows in by_category.items():
        if len(rows) < 2:
            continue
        rows_sorted = sorted(rows, key=lambda a: a.get("roas", 0), reverse=True)
        leader, laggard = rows_sorted[0], rows_sorted[-1]
        if leader["property"] == laggard["property"] or leader["roas"] <= laggard["roas"]:
            continue
        out.append(Suggestion(
            slug=f"sg-crossprop-{category}-{laggard['property']}", category="cross_property",
            title=f"Try {leader['property']}'s \"{category}\" approach at {laggard['property']}",
            rationale=f"{leader['property']} gets {leader['roas']:.1f}x on {category}; "
                     f"{laggard['property']} gets {laggard['roas']:.1f}x on the same "
                     f"category - worth testing the winning angle.",
            impact=f"{leader['property']} — {leader['roas']:.1f}x",
            evidence=[Evidence("asset", leader["slug"], leader.get("headline", leader["slug"]))],
        ))
    return out


def generate_suggestions(ads: list[dict], events: list[dict], reviews: list[dict],
                         cfg: dict) -> list[Suggestion]:
    rules = cfg.get("rules", {})
    scfg = cfg.get("suggestions", {})
    radar_on = rules.get("event_radar", True)
    out: list[Suggestion] = []
    out += _event_suggestions(events, ads, radar_on)
    out += _headline_test_suggestions(ads, scfg.get("headline_min_age_days", 60))
    out += _review_ad_suggestions(reviews, scfg.get("review_min_mentions", 3))
    out += _budget_shift_suggestions(ads, cfg.get("budget", {}).get("twin_pairs", []),
                                     cfg.get("budget", {}).get("twin_roas_gap_min", 2.0))
    out += _landing_page_suggestions(ads)
    out += _cross_property_suggestions(ads)
    return out
