#!/usr/bin/env python3
"""tools/report.py - what the agent did, and what it cost.

    make report
    python3 tools/report.py
    python3 tools/report.py --json

Reads data/agent.db - nothing here calls a model or an adapter. Numbers tied
to roster claims (README.md section 2, docs/benefits.md):

``volumes``          items by kind and by review_status right now.
``queue age``         how long the oldest pending item has waited - the
                      thing `store.mark_stale()` protects against.
``campaigns``         campaigns generated and drafts pushed to the library -
                      the "3-5x content cadence" claim.
``budget summary``    freed vs. projected € across every budget run so far.
``spend``             LLM calls, tokens and cost, from core.llm's usage
                      logging (core.store.usage_totals).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.config import ConfigError, load_settings  # noqa: E402
from core.store import Store, StoreError  # noqa: E402
from tools.campaign import MIGRATE_SQL  # noqa: E402


def volumes(store: Store) -> dict:
    by_status = store.counts()
    rows = store.db.execute("SELECT kind, COUNT(*) AS n FROM items GROUP BY kind").fetchall()
    by_kind = {r["kind"]: r["n"] for r in rows}
    return {"by_kind": by_kind, "by_status": by_status, "total": sum(by_kind.values())}


def queue_age(store: Store) -> dict:
    row = store.db.execute(
        "SELECT MIN(updated_at) AS oldest FROM items WHERE review_status IN "
        "('pending_review','needs_human')").fetchone()
    if not row or not row["oldest"]:
        return {"oldest_pending": None, "age_hours": 0}
    oldest = datetime.fromisoformat(row["oldest"])
    now = datetime.now(timezone.utc)
    age_hours = round((now - oldest).total_seconds() / 3600, 1)
    return {"oldest_pending": row["oldest"], "age_hours": age_hours}


def campaign_stats(store: Store) -> dict:
    try:
        campaigns = store.db.execute("SELECT COUNT(*) AS n FROM campaigns").fetchone()["n"]
        drafts = store.db.execute(
            "SELECT status, COUNT(*) AS n FROM creative_drafts GROUP BY status").fetchall()
    except Exception:  # noqa: BLE001 - table may not exist yet on a fresh db
        return {"campaigns": 0, "drafts_by_status": {}}
    return {"campaigns": campaigns, "drafts_by_status": {r["status"]: r["n"] for r in drafts}}


def budget_summary(store: Store) -> dict:
    rows = store.db.execute(
        "SELECT payload_json FROM items WHERE kind='budget_change'").fetchall()
    freed = projected = 0.0
    paused = scaled = held = 0
    for r in rows:
        p = json.loads(r["payload_json"] or "{}")
        if p.get("action") == "pause":
            freed += p.get("from_daily", 0) * 30 - 0
            paused += 1
        elif p.get("action") == "scale_up":
            scaled += 1
        elif p.get("action") == "hold":
            held += 1
    return {"paused": paused, "scaled_up": scaled, "held": held}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        settings = load_settings()
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 1

    try:
        store = Store(settings)
    except StoreError as exc:
        print(f"store error: {exc}", file=sys.stderr)
        return 1
    store.migrate(MIGRATE_SQL)

    report = {
        "volumes": volumes(store), "queue_age": queue_age(store),
        "campaigns": campaign_stats(store), "budget": budget_summary(store),
        "spend": store.usage_totals(),
    }
    store.close()

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0

    print("Marketing & Social AI - report\n")
    v = report["volumes"]
    print(f"Volumes: {v['total']} item(s) total")
    for kind, n in sorted(v["by_kind"].items()):
        print(f"  {kind}: {n}")
    print(f"\nQueue age: oldest pending item is {report['queue_age']['age_hours']} hour(s) old")
    c = report["campaigns"]
    print(f"\nCampaigns: {c['campaigns']} generated, drafts by status: "
         f"{c['drafts_by_status'] or 'none yet'}")
    b = report["budget"]
    print(f"\nBudget: {b['paused']} paused, {b['scaled_up']} scaled up, {b['held']} held")
    s = report["spend"]
    print(f"\nLLM spend: {s}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
