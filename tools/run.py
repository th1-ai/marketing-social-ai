#!/usr/bin/env python3
"""tools/run.py - Marketing & Social AI's main loop and three sub-agent passes.

    python3 tools/run.py --once                  # suggestion queue (default)
    python3 tools/run.py --once --budget          # budget optimizer
    python3 tools/run.py --once --content         # Content Creation AI (Editor)
    python3 tools/run.py --once --design          # Brand & Collateral AI (Art Director)
    python3 tools/run.py --once --performance     # Marketing Performance AI (Attributor)
    python3 tools/run.py --watch [--budget|...]
    python3 tools/run.py --once --dry-run

Every kind this agent produces (suggestion, budget_change, design_request,
roas_alert, exec_report) lands at `pending_review` or `skipped` - there is
no auto-send path anywhere in this agent (docs/how-it-works.md "Design
decisions" #12). `tools/review.py send` is what actually calls the ads
adapter, notifies staff, or emails the manager, always through
`core.review`'s write guard.

Exit codes: 0 ok, 3 waiting on an `interactive` narrative answer, 1 a real error.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.adapters import get_email  # noqa: E402
from core.adapters.base import AdapterError  # noqa: E402
from core.config import ConfigError, load_settings  # noqa: E402
from core.llm import LLMError, LLMPendingInteractive, complete  # noqa: E402
from core.log import Run, get_logger, summary_line  # noqa: E402
from core.review import WriteBlocked  # noqa: E402
from core.store import Store, StoreError  # noqa: E402
from core.templates import build_prompt  # noqa: E402
from tools import ingest  # noqa: E402
from tools.attribution_engine import build_exec_report, find_roas_drops  # noqa: E402
from tools.budget_engine import analyse_budget  # noqa: E402
from tools.campaign import MIGRATE_SQL, file_content_flag, generate_for_brief  # noqa: E402
from tools.content_engine import Brief, parse_freestyle  # noqa: E402
from tools.design_engine import draft_design_request  # noqa: E402
from tools.suggestion_engine import generate_suggestions  # noqa: E402

log = get_logger("run")


def _narrate(task: str, fixture_id: str, item: dict, settings, store, provider: str | None):
    """Best-effort: a narration failure never fails a run that already succeeded."""
    schema = json.loads(
        (REPO_ROOT / "prompts" / "schemas" / f"{task}.json").read_text(encoding="utf-8"))
    prompt = build_prompt(task, settings=settings, item=item, fixture_id=fixture_id)
    try:
        result = complete(task, prompt, schema, settings=settings, provider=provider,
                          store=None if settings.dry_run else store)
        return (result.data or {}).get("note")
    except LLMPendingInteractive:
        raise
    except LLMError as exc:
        log.warn(f"{task} skipped", error=str(exc)[:200])
        return None


def one_pass_suggestions(settings, store, *, today: str | None = None) -> tuple[int, dict]:
    stats = {"processed": 0, "skipped": 0, "pending_review": 0}
    cfg = settings.agent
    today = today or date.today().isoformat()
    with Run("suggestions", settings, None if settings.dry_run else store) as run:
        ads_raw = ingest.load_marketing_assets()
        perf = ingest.load_ad_performance()
        ads = [{**a, **ingest.aggregate_30d(perf, a["slug"], as_of=today)}
              for a in ads_raw if a.get("kind") in ("meta_ad", "google_ad")
              and a.get("status") == "active"]
        events = ingest.load_events()
        reviews = ingest.load_reviews()
        suggestions = generate_suggestions(ads, events, reviews, cfg)
        if settings.dry_run:
            stats["processed"] = len(suggestions)
        else:
            for s in suggestions:
                payload = {"category": s.category, "title": s.title, "rationale": s.rationale,
                          "impact": s.impact, "evidence": [e.__dict__ for e in s.evidence],
                          "prefilled_brief": s.prefilled_brief}
                item, created = store.upsert_unique("suggestion", s.slug, payload,
                                                    source="suggestion_engine")
                if not created:
                    stats["skipped"] += 1
                    continue
                stats["processed"] += 1
                store.set_fields(item.id, draft=payload)
                if s.muted:
                    store.transition(item.id, "skipped", "agent",
                                     {"reason": "muted by rule: event-radar off"})
                    stats["skipped"] += 1
                    continue
                store.transition(item.id, "dispatched", "agent")
                store.transition(item.id, "pending_review", "agent")
                stats["pending_review"] += 1
            stale = store.mark_stale(72)
            if stale:
                log.info("marked stale", count=len(stale))
        stats["drafted"] = stats["processed"]
        run.stats = dict(stats)
    print(f"  {len(suggestions)} suggestion(s) considered "
         f"({stats['pending_review']} queued, {stats['skipped']} skipped/muted).")
    return 0, stats


def one_pass_budget(settings, store, *, provider: str | None,
                    today: str | None = None) -> tuple[int, dict]:
    stats = {"processed": 0, "skipped": 0, "pending_review": 0, "sent": 0}
    cfg = settings.agent
    today = today or date.today().isoformat()
    with Run("budget", settings, None if settings.dry_run else store) as run:
        ads_raw = {a["slug"]: a for a in ingest.load_marketing_assets()
                  if a.get("kind") in ("meta_ad", "google_ad") and a.get("status") == "active"
                  and a.get("daily_budget")}
        perf = ingest.load_ad_performance()
        ads = []
        for slug, a in ads_raw.items():
            agg = ingest.aggregate_30d(perf, slug, as_of=today)
            ads.append({"slug": slug, "name": a.get("name", slug),
                       "platform": a.get("platform", "meta"), "daily_budget": a["daily_budget"],
                       "ctr": agg["ctr_pct"], "spend": agg["spend"], "revenue": agg["revenue"],
                       "roas": agg["roas"]})
        result = analyse_budget(ads, cfg)
        if settings.dry_run:
            stats["processed"] = len(result.changes)
        else:
            for c in result.changes:
                payload = {"asset_slug": c.asset_slug, "platform": c.platform,
                          "action": c.action, "from_daily": c.from_daily,
                          "to_daily": c.to_daily, "reason": c.reason,
                          "projected_delta_monthly": c.projected_delta_monthly}
                item, created = store.upsert_unique("budget_change", c.unique_key(today),
                                                    payload, source="budget_engine")
                if not created:
                    stats["skipped"] += 1
                    continue
                stats["processed"] += 1
                store.set_fields(item.id, draft=payload)
                if c.action == "hold":
                    store.transition(item.id, "skipped", "agent",
                                     {"reason": "hold: demand-capped, never scaled"})
                    stats["skipped"] += 1
                    continue
                store.transition(item.id, "dispatched", "agent")
                store.transition(item.id, "pending_review", "agent")
                stats["pending_review"] += 1
        stats["drafted"] = stats["processed"]
        run.stats = {**stats, "summary": result.summary}
        try:
            note = _narrate("budget_note", "budget-note-01", {"summary": result.summary},
                           settings, store, provider)
            if note:
                print(f"\nNote: {note}\n")
        except LLMPendingInteractive as exc:
            print(str(exc))
            return 3, stats
    for line in result.thinking_log:
        print(f"  - {line}")
    return 0, stats


def one_pass_content(settings, store, *, provider: str | None) -> tuple[int, dict]:
    if not settings.agent_get("subagents.content_creation.enabled", False):
        print("Content Creation AI is off - enable subagents.content_creation.enabled "
             "in config/agent.yaml. See workflows/21-content-creation.md.")
        return 0, {}
    cfg = settings.agent
    properties = cfg.get("properties", {})
    default_property = next(iter(properties), "")
    stats = {"processed": 0, "skipped": 0, "needs_human": 0}
    hotel_languages = tuple(settings.hotel.languages)
    with Run("content_creation", settings, None if settings.dry_run else store) as run:
        candidates = store.list_items(status="approved", kind="suggestion", limit=50)
        candidates = [c for c in candidates
                     if (c.payload or {}).get("category") in ("event_signal", "new_creative")
                     and not (c.payload or {}).get("_campaign_id")]
        content_assets = ingest.load_content_assets()
        property_keywords = {slug: p.get("name", slug).lower()
                            for slug, p in properties.items()}
        for cand in candidates:
            brief_text = (cand.payload or {}).get("prefilled_brief") or (cand.payload or {}).get(
                "title", "")
            brief = parse_freestyle(brief_text, property_keywords, default_property)
            if settings.dry_run:
                stats["processed"] += 1
                continue
            property_label = properties.get(brief.property_slug, {}).get(
                "name", brief.property_slug)
            campaign_id, result = generate_for_brief(store, brief, content_assets,
                                                      cfg.get("rules", {}), property_label,
                                                      source_suggestion=cand.id,
                                                      hotel_languages=hotel_languages)
            store.set_fields(cand.id, payload={**cand.payload, "_campaign_id": campaign_id})
            stats["processed"] += 1
            print(f"  generated campaign {campaign_id} for suggestion {cand.id} "
                 f"({len(result.creatives)} creatives).")
            if result.needs_human:
                flag_id = file_content_flag(store, campaign_id, brief, result)
                stats["needs_human"] += 1
                print(f"  needs a human: {' '.join(result.needs_human_reasons)} "
                     f"(filed {flag_id})")
            off_brand = sum(1 for c in result.creatives if c.off_brand)
            try:
                note = _narrate("campaign_note", "campaign-note-01",
                               {"name": campaign_id,
                                "headlines": [c.headline for c in result.creatives[:4]],
                                "photos": list({c.photo_slug for c in result.creatives}),
                                "off_brand": off_brand}, settings, store, provider)
                if note:
                    print(f"  Note: {note}")
            except LLMPendingInteractive as exc:
                print(str(exc))
                return 3, stats
        run.stats = dict(stats)
    if not candidates:
        print("  no approved suggestion is waiting for a campaign.")
    return 0, stats


def one_pass_design(settings, store) -> tuple[int, dict]:
    if not settings.agent_get("subagents.brand_collateral.enabled", False):
        print("Brand & Collateral AI is off - enable subagents.brand_collateral.enabled "
             "in config/agent.yaml. See workflows/22-brand-collateral.md.")
        return 0, {}
    cfg = settings.agent
    properties = cfg.get("properties", {})
    stats = {"processed": 0, "skipped": 0, "pending_review": 0}
    with Run("brand_collateral", settings, None if settings.dry_run else store) as run:
        open_requests = store.list_items(status="new", kind="design_request", limit=50)
        content_assets = ingest.load_content_assets()
        for item in open_requests:
            payload = item.payload or {}
            property_label = properties.get(payload.get("property_slug", ""), {}).get(
                "name", payload.get("property_slug", ""))
            if settings.dry_run:
                stats["processed"] += 1
                continue
            draft = draft_design_request(payload, content_assets, cfg.get("rules", {}),
                                         property_label)
            draft_payload = {**payload, "title": draft.title, "notes": draft.notes,
                            "creative": draft.creative.__dict__ if draft.creative else None,
                            "thinking_log": draft.thinking_log}
            store.set_fields(item.id, draft=draft_payload)
            store.transition(item.id, "dispatched", "agent")
            store.transition(item.id, "pending_review", "agent")
            stats["processed"] += 1
            stats["pending_review"] += 1
        run.stats = dict(stats)
    if not open_requests:
        print("  no open design request is waiting.")
    else:
        print(f"  drafted {stats['pending_review']} design request(s).")
    return 0, stats


def one_pass_performance(settings, store, *, today: str | None = None) -> tuple[int, dict]:
    if not settings.agent_get("subagents.marketing_performance.enabled", False):
        print("Marketing Performance AI is off - enable "
             "subagents.marketing_performance.enabled in config/agent.yaml. "
             "See workflows/23-marketing-performance.md.")
        return 0, {}
    cfg = settings.agent
    mp_cfg = cfg.get("subagents", {}).get("marketing_performance", {})
    today = today or date.today().isoformat()
    stats = {"processed": 0, "skipped": 0, "pending_review": 0}
    with Run("marketing_performance", settings, None if settings.dry_run else store) as run:
        perf = ingest.load_ad_performance()
        slugs = sorted({r["asset_slug"] for r in perf})
        alerts = find_roas_drops(perf, slugs, today, mp_cfg.get("roas_drop_alert_pct", 0.25))
        if settings.dry_run:
            stats["processed"] = len(alerts)
        else:
            for a in alerts:
                payload = a.__dict__
                item, created = store.upsert_unique("roas_alert", a.unique_key(today), payload,
                                                    source="attribution_engine")
                if not created:
                    stats["skipped"] += 1
                    continue
                stats["processed"] += 1
                store.set_fields(item.id, draft=payload)
                store.transition(item.id, "dispatched", "agent")
                store.transition(item.id, "pending_review", "agent")
                stats["pending_review"] += 1

            kpis = _kpi_strip(perf, today)
            report = build_exec_report(settings.hotel.name, kpis, alerts, store.counts(), today)
            export_path = REPO_ROOT / "data" / "exports" / f"exec_report_{today}.md"
            export_path.parent.mkdir(parents=True, exist_ok=True)
            export_path.write_text(report, encoding="utf-8")
            print(f"  exported {export_path.relative_to(REPO_ROOT)}")

            manager_email = (settings.contacts.manager or {}).get("email", "")
            if manager_email:
                subject = f"Marketing performance — {settings.hotel.name}, {today}"
                payload = {"to": manager_email, "subject": subject, "body": report}
                item, created = store.upsert_unique("exec_report", today, payload,
                                                    source="attribution_engine")
                if created:
                    stats["processed"] += 1
                    store.set_fields(item.id, draft=payload)
                    store.transition(item.id, "dispatched", "agent")
                    store.transition(item.id, "pending_review", "agent")
                    stats["pending_review"] += 1
        run.stats = dict(stats)
    print(f"  {len(alerts)} ROAS-drop alert(s).")
    return 0, stats


def _kpi_strip(perf: list[dict], as_of: str) -> dict:
    slugs = {r["asset_slug"] for r in perf}
    spend = revenue = bookings = impressions = clicks = 0.0
    for slug in slugs:
        agg = ingest.aggregate_30d(perf, slug, days=90, as_of=as_of)
        spend += agg["spend"]
        revenue += agg["revenue"]
        bookings += agg["bookings"]
        impressions += agg["impressions"]
        clicks += agg["clicks"]
    return {"spend": spend, "revenue": revenue, "bookings": bookings,
           "roas": round(revenue / spend, 2) if spend else 0.0,
           "ctr_pct": round(100 * clicks / impressions, 2) if impressions else 0.0,
           "cpc": round(spend / clicks, 2) if clicks else 0.0}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--once", action="store_true", help="run a single pass (default)")
    mode_group.add_argument("--watch", action="store_true",
                            help="keep running on the configured interval")
    pass_group = parser.add_mutually_exclusive_group()
    pass_group.add_argument("--budget", action="store_true", help="run the budget optimizer")
    pass_group.add_argument("--content", action="store_true",
                            help="run Content Creation AI's queued-brief pass")
    pass_group.add_argument("--design", action="store_true",
                            help="run Brand & Collateral AI's design-request pass")
    pass_group.add_argument("--performance", action="store_true",
                            help="run Marketing Performance AI's alert + exec-report pass")
    parser.add_argument("--dry-run", action="store_true",
                        help="compute everything, write nothing, even in live mode")
    parser.add_argument("--provider", default=None, help="override llm.provider for this run")
    parser.add_argument("--as-of", default=None,
                        help="override today's date (YYYY-MM-DD) - mainly for tests/demo")
    parser.add_argument("--poll-seconds", type=int, default=None,
                        help="override the --watch interval")
    args = parser.parse_args(argv)

    try:
        settings = load_settings(provider=args.provider, dry_run=args.dry_run)
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 1

    try:
        store = Store(settings)
    except StoreError as exc:
        print(f"store error: {exc}", file=sys.stderr)
        return 1
    store.migrate(MIGRATE_SQL)
    try:
        def pass_fn():
            if args.budget:
                return one_pass_budget(settings, store, provider=args.provider,
                                       today=args.as_of)
            if args.content:
                return one_pass_content(settings, store, provider=args.provider)
            if args.design:
                return one_pass_design(settings, store)
            if args.performance:
                return one_pass_performance(settings, store, today=args.as_of)
            return one_pass_suggestions(settings, store, today=args.as_of)

        if args.watch:
            poll_seconds = args.poll_seconds or int(settings.agent_get("poll_seconds", 3600))
            while True:
                code, stats = pass_fn()
                print(summary_line({"processed": stats.get("processed", 0),
                                    "drafted": stats.get("processed", 0),
                                    "sent": stats.get("sent", 0)}, settings.mode))
                if code != 0:
                    return code
                time.sleep(poll_seconds)
        code, stats = pass_fn()
        print(summary_line({"processed": stats.get("processed", 0),
                            "drafted": stats.get("processed", 0),
                            "sent": stats.get("sent", 0)}, settings.mode))
        return code
    except (LLMError, AdapterError, StoreError, WriteBlocked) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
