"""tools/attribution_engine.py - Marketing Performance AI's reporting layer.

The source has no engine of its own (concept status, specs/marketing-
performance-ai.md: "no dedicated engine function... reads the same tables
the parent's budget optimiser also reads"). This module is the honest v1
named in that spec's "Open questions" #1: real ROAS-drop alerting and a
Monday exec report, built from the same 30-day aggregates
`tools/ingest.aggregate_30d` already produces for the budget desk.

Pure functions: no I/O, no LLM. `tools/run.py --performance` is the only
place that writes an alert or exports the report.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any


@dataclass
class RoasAlert:
    asset_slug: str
    trailing_roas: float
    prior_roas: float
    drop_pct: float
    reason: str

    def unique_key(self, run_date: str) -> str:
        return f"{run_date}:{self.asset_slug}"


def week_over_week_roas(rows: list[dict], asset_slug: str, as_of: str) -> tuple[float, float]:
    """(trailing 7-day ROAS, prior 7-day ROAS) for one asset, ending ``as_of``."""
    end = date.fromisoformat(as_of)
    trailing_start = (end - timedelta(days=6)).isoformat()
    prior_end = (end - timedelta(days=7)).isoformat()
    prior_start = (end - timedelta(days=13)).isoformat()

    def window_roas(start: str, stop: str) -> float:
        matched = [r for r in rows if r.get("asset_slug") == asset_slug and start <= r["date"] <= stop]
        spend = sum(r.get("spend", 0) for r in matched)
        revenue = sum(r.get("revenue", 0) for r in matched)
        return round(revenue / spend, 2) if spend else 0.0

    return window_roas(trailing_start, as_of), window_roas(prior_start, prior_end)


def find_roas_drops(rows: list[dict], asset_slugs: list[str], as_of: str,
                    drop_pct_threshold: float = 0.25) -> list[RoasAlert]:
    """A creative whose trailing week fell more than ``drop_pct_threshold``
    against the week before it - a plain, explainable comparison, not a
    statistical model (docs/how-it-works.md "Design decisions" #7)."""
    out = []
    for slug in asset_slugs:
        trailing, prior = week_over_week_roas(rows, slug, as_of)
        if prior <= 0:
            continue
        drop = round((prior - trailing) / prior, 3)
        if drop >= drop_pct_threshold:
            out.append(RoasAlert(
                asset_slug=slug, trailing_roas=trailing, prior_roas=prior, drop_pct=drop,
                reason=f"ROAS fell from {prior:.1f}x to {trailing:.1f}x this week "
                      f"({drop * 100:.0f}% drop) - worth a look before more spends against it."))
    return out


def build_exec_report(hotel_name: str, kpis: dict, alerts: list[RoasAlert],
                      queue_counts: dict, as_of: str) -> str:
    """One markdown digest: KPI strip, ROAS-drop alerts, what's waiting in the
    queue. Always exported (never gated); emailing it is a separate, guarded
    step in tools/run.py."""
    lines = [f"# {hotel_name} — marketing performance, {as_of}", ""]
    lines.append("## The numbers (90-day window)")
    lines.append(f"- Ad spend: €{kpis.get('spend', 0):,.0f}")
    lines.append(f"- Attributed revenue: €{kpis.get('revenue', 0):,.0f} "
                f"({kpis.get('bookings', 0)} bookings)")
    lines.append(f"- Blended ROAS: {kpis.get('roas', 0):.1f}x")
    lines.append(f"- Blended CTR / CPC: {kpis.get('ctr_pct', 0):.1f}% / €{kpis.get('cpc', 0):.2f}")
    lines.append("")
    lines.append("## ROAS drops this week")
    if alerts:
        for a in alerts:
            lines.append(f"- **{a.asset_slug}**: {a.reason}")
    else:
        lines.append("- None. Every creative held or improved its return week over week.")
    lines.append("")
    lines.append("## Waiting for you")
    for status, count in sorted(queue_counts.items()):
        if count:
            lines.append(f"- {count} {status.replace('_', ' ')}")
    if not any(queue_counts.values()):
        lines.append("- Nothing. The queue is clear.")
    lines.append("")
    lines.append("Doesn't move budgets itself - these numbers feed the budget desk, "
                "where changes apply only inside safety caps and with your approval.")
    return "\n".join(lines)
