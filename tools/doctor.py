#!/usr/bin/env python3
"""tools/doctor.py - is Marketing & Social AI configured and reachable right now?

    make doctor
    python3 tools/doctor.py

Runs the generic core.doctor checks (python, deps, config, .env, hotel
identity, mode, llm provider, every core adapter, the store, knowledge) plus
this agent's own: the six rules toggles, the twin pairs in the budget
config, which signal each of ad performance/content assets/reviews/events is
actually reading from (a real import, or the demo fixtures), the ads
adapter, and which of the three sub-agents are on. Exits 0 when everything
passed, 1 when a FAIL line needs fixing. Never a traceback.

The generic "pms adapter" check is replaced with `check_pms_not_used()`:
`config/hotel.yaml: systems.pms` is shared across the whole agent family,
but this agent's own `tools/` never call the PMS (docs/integrations.md), so
missing Cloudbeds/Mews/etc. credentials should never fail `make doctor` here.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.config import ConfigError, Settings, load_settings  # noqa: E402
from core.doctor import Check, FAIL, PASS, WARN, print_table, run_checks  # noqa: E402
from tools import ingest  # noqa: E402
from tools.ads_adapters import get_ads  # noqa: E402


def check_properties(settings: Settings) -> Check:
    properties = settings.agent_get("properties", {})
    if not properties:
        return Check("properties", FAIL, "no properties in config/agent.yaml",
                     "Copy config/agent.example.yaml to config/agent.yaml and list your "
                     "own propert(y/ies).")
    return Check("properties", PASS, f"{len(properties)}: {', '.join(properties)}")


def check_rules(settings: Settings) -> Check:
    rules = settings.agent_get("rules", {})
    off = [k for k, v in rules.items() if not v]
    return Check("marketing rules", PASS,
                 f"{len(rules)} rule(s)" + (f", off: {', '.join(off)}" if off else ", all on"))


def check_twin_pairs(settings: Settings) -> Check:
    pairs = settings.agent_get("budget.twin_pairs", [])
    if not pairs:
        return Check("twin pairs", WARN, "no budget.twin_pairs configured",
                     "The budget optimizer's phase 2 (settle the A/B twins) has nothing "
                     "to compare. Add (loser, winner) slug pairs in config/agent.yaml.")
    return Check("twin pairs", PASS, f"{len(pairs)} pair(s): "
                 f"{', '.join(f'{a}->{b}' for a, b in pairs)}")


def check_pms_not_used() -> Check:
    """Replace `core.doctor`'s generic "pms adapter" check for this agent.

    `config/hotel.yaml: systems.pms` is shared across the whole agent
    family, but `docs/integrations.md` ("PMS, Sheets, GA4, Search Console")
    says plainly that nothing in this repo's `tools/` calls the PMS
    adapter at all - so a hotel that only runs Marketing & Social AI should
    never burn time chasing Cloudbeds/Mews/etc. credentials this agent will
    never touch. The generic check still runs (see `main()`); this replaces
    its result rather than skipping it, so the line stays in the table
    instead of silently disappearing.
    """
    return Check("pms adapter", PASS, "not used by this agent - Marketing & Social AI's "
                 "tools/ never call the PMS (see docs/integrations.md)")


def check_ads_adapter(settings: Settings) -> Check:
    try:
        ads = get_ads(settings)
    except Exception as exc:  # noqa: BLE001
        return Check("ads adapter", FAIL, str(exc)[:200], "")
    health = ads.ping()
    status = PASS if health.ok else (WARN if ads.status == "stub" else FAIL)
    return Check("ads adapter", status, f"{ads.name} [{ads.status}] {health.detail}",
                 health.fix_hint)


def check_signals() -> Check:
    sources = ingest.sources_used()
    none_imported = [k for k, v in sources.items() if v.startswith("demo fixtures")]
    detail = "; ".join(f"{k}: {v}" for k, v in sources.items())
    if none_imported:
        return Check("signal sources", WARN, detail,
                     "No data/imports/*.json for "
                     f"{', '.join(none_imported)} - the engine reads the demo fixtures "
                     "instead. See docs/integrations.md.")
    return Check("signal sources", PASS, detail)


def check_subagents(settings: Settings) -> Check:
    editor = settings.agent_get("subagents.content_creation.enabled", False)
    art_director = settings.agent_get("subagents.brand_collateral.enabled", False)
    attributor = settings.agent_get("subagents.marketing_performance.enabled", False)
    return Check("sub-agents", PASS,
                 f"Content Creation AI {'on' if editor else 'off'}, "
                 f"Brand & Collateral AI {'on' if art_director else 'off'}, "
                 f"Marketing Performance AI {'on' if attributor else 'off'}")


def check_prompts() -> Check:
    missing = [p for p in ("prompts/budget_note.md", "prompts/campaign_note.md",
                           "prompts/copilot_ask.md", "prompts/schemas/budget_note.json",
                           "prompts/schemas/campaign_note.json",
                           "prompts/schemas/copilot_ask.json")
              if not (REPO_ROOT / p).is_file()]
    if missing:
        return Check("prompts", FAIL, f"missing {', '.join(missing)}",
                     "These ship with the repo - restore them from git.")
    return Check("prompts", PASS, "budget_note.md + campaign_note.md + copilot_ask.md present")


def main() -> int:
    try:
        settings = load_settings()
    except ConfigError as exc:
        checks = run_checks(None) + [Check("config", FAIL, str(exc),
                                           "Fix config/hotel.yaml or config/agent.yaml.")]
        return print_table(checks, title="Marketing & Social AI - doctor")

    checks = run_checks(settings, extra=[check_properties, check_rules, check_twin_pairs,
                                         check_ads_adapter, check_subagents])
    # core.doctor's generic "pms adapter" check hard-FAILs on missing PMS
    # credentials - not relevant here, this agent never calls the PMS. See
    # check_pms_not_used().
    checks = [check_pms_not_used() if c.name == "pms adapter" else c for c in checks]
    checks.append(check_prompts())
    checks.append(check_signals())
    return print_table(checks, title="Marketing & Social AI - doctor")


if __name__ == "__main__":
    raise SystemExit(main())
