"""tools/budget_engine.py - the Bard's budget optimizer. Pure functions.

No I/O anywhere in this file: `analyse_budget` takes a list of plain dicts
(the 30-day aggregates from `tools/ingest.aggregate_30d`) and a config dict,
and returns `BudgetResult` - a list of `BudgetChange` plus a thinking log and
a summary. `tools/run.py` is the only place that writes to the store or
calls the ads adapter. See docs/how-it-works.md "The budget steps" for the
narrative version of every rule below; every number here is ported from the
source engine unchanged.

Nothing here ever marks a change auto-appliable: the roster's promise is
unconditional ("Won't post or move a budget without approval"), so every
change this function returns waits for a human, whatever `autonomy` says in
config/agent.yaml. That is enforced in `tools/run.py`, not here - this file
only computes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def round5(value: float) -> float:
    return max(5, round(value / 5) * 5)


@dataclass
class BudgetChange:
    asset_slug: str
    platform: str  # meta | google
    action: str  # scale_up | pause | reallocate | hold
    from_daily: float
    to_daily: float
    reason: str
    projected_delta_monthly: float

    def unique_key(self, run_date: str) -> str:
        return f"{run_date}:{self.asset_slug}:{self.action}"


@dataclass
class BudgetResult:
    changes: list[BudgetChange]
    thinking_log: list[str]
    summary: dict[str, Any]


def analyse_budget(ads: list[dict], cfg: dict) -> BudgetResult:
    """``ads``: rows of {slug, name, platform, daily_budget, spend, revenue,
    roas, ctr}, one per active ad with a daily budget, already aggregated
    over the last 30 days (``tools/ingest.aggregate_30d``)."""
    bcfg = cfg.get("budget", {})
    cap_on = cfg.get("rules", {}).get("budget_safety_cap", True)
    scale_factor = bcfg.get("scale_factor_capped" if cap_on else "scale_factor_uncapped",
                            2 if cap_on else 3)
    pause_below = bcfg.get("pause_below_roas_capped" if cap_on else "pause_below_roas_uncapped",
                          1.0 if cap_on else 1.5)
    pause_min_spend = bcfg.get("pause_min_spend_30d", 900)
    scale_roas_min = bcfg.get("scale_up_roas_min", 7.0)
    scale_budget_max = bcfg.get("scale_up_daily_budget_max", 200)
    hold_roas_above = bcfg.get("hold_roas_above", 20)
    twin_pairs = bcfg.get("twin_pairs", [])
    twin_gap_min = bcfg.get("twin_roas_gap_min", 2.0)
    twin_shift_pct = bcfg.get("twin_shift_pct", 0.4)

    by_slug = {a["slug"]: a for a in ads}
    ordered = sorted(ads, key=lambda a: a["spend"], reverse=True)
    handled: set[str] = set()
    changes: list[BudgetChange] = []
    log: list[str] = []

    total_spend = round(sum(a["spend"] for a in ads), 2)
    log.append(f"Pulled 30-day funnels: {len(ads)} active ad(s), €{total_spend} spent.")
    if ads:
        lo = min(a["roas"] for a in ads)
        hi = max(a["roas"] for a in ads)
        log.append(f"Ranked return: {lo:.1f}x to {hi:.1f}x.")

    # Phase 1 - stop the bleeding.
    paused = 0
    freed = 0.0
    for a in ordered:
        if a["roas"] < pause_below and a["spend"] > pause_min_spend:
            delta = round(a["spend"] - a["revenue"], 2)
            reason = (f"€{a['spend']} spent in 30 days with zero attributed bookings - "
                     f"pause and rebuild the creative" if a["revenue"] == 0 else
                     f"{a['roas']:.1f}x return after €{a['spend']} spend - below the "
                     f"{pause_below:.1f}x line.")
            changes.append(BudgetChange(a["slug"], a["platform"], "pause",
                                        a["daily_budget"], 0, reason, delta))
            handled.add(a["slug"])
            paused += 1
            freed += delta
    log.append(f"Stopped the bleeding: {paused} paused, €{round(freed)} freed.")

    # Phase 2 - settle the A/B twins.
    settled = 0
    for loser_slug, winner_slug in twin_pairs:
        loser, winner = by_slug.get(loser_slug), by_slug.get(winner_slug)
        if not loser or not winner or loser_slug in handled or winner_slug in handled:
            continue
        if winner["roas"] - loser["roas"] < twin_gap_min:
            continue
        shift = round5(loser["daily_budget"] * twin_shift_pct)
        changes.append(BudgetChange(loser_slug, loser["platform"], "reallocate",
                                    loser["daily_budget"], loser["daily_budget"] - shift,
                                    f"{winner['ctr']:.1f}% vs {loser['ctr']:.1f}% CTR - "
                                    f"shifting budget to the winner", 0))
        delta = round(shift * 30 * (winner["roas"] - loser["roas"]) * 0.6)
        changes.append(BudgetChange(winner_slug, winner["platform"], "reallocate",
                                    winner["daily_budget"], winner["daily_budget"] + shift,
                                    f"{winner['ctr']:.1f}% vs {loser['ctr']:.1f}% CTR - "
                                    f"outperforming its twin", delta))
        handled.update((loser_slug, winner_slug))
        settled += 1
    log.append(f"Settled the A/B twins: {settled} pair(s) rebalanced.")

    # Phase 3 - feed the winners.
    scaled, held = 0, 0
    for a in ordered:
        if a["slug"] in handled:
            continue
        if a["roas"] > hold_roas_above:
            changes.append(BudgetChange(a["slug"], a["platform"], "hold",
                                        a["daily_budget"], a["daily_budget"],
                                        f"{a['roas']:.1f}x - but these are brand-term "
                                        f"searches. Demand-capped; extra budget buys the "
                                        f"same clicks for more.", 0))
            held += 1
            handled.add(a["slug"])
        elif a["roas"] >= scale_roas_min and a["daily_budget"] <= scale_budget_max:
            to_daily = round5(a["daily_budget"] * scale_factor)
            delta = round((to_daily - a["daily_budget"]) * 30 * a["roas"] * 0.8)
            changes.append(BudgetChange(a["slug"], a["platform"], "scale_up",
                                        a["daily_budget"], to_daily,
                                        f"{a['roas']:.1f}x on €{a['daily_budget']}/day - "
                                        f"scaling {scale_factor}x "
                                        f"{'inside' if cap_on else 'OUTSIDE'} the safety caps.",
                                        delta))
            scaled += 1
            handled.add(a["slug"])
    log.append(f"Fed the winners: {scaled} scaled up "
              f"({scale_factor}x {'inside' if cap_on else 'OUTSIDE'} the caps), "
              f"{held} held (brand terms, demand-capped).")

    actionable = [c for c in changes if c.action != "hold"]
    projected = round(sum(c.projected_delta_monthly for c in changes))
    log.append(f"Drafted the order: {len(actionable)} moves, projected "
              f"+€{projected}/month. Nothing applies until you say so.")

    summary = {"proposals": len(actionable), "freed_monthly": round(freed),
              "projected_monthly_delta": projected, "caps_off": not cap_on}
    return BudgetResult(changes=changes, thinking_log=log, summary=summary)
