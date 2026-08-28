#!/usr/bin/env python3
"""tools/demo.py - the whole loop on the bundled fixtures, zero credentials.

    make demo
    python3 tools/demo.py

Uses `load_settings(demo=True)`: mock provider, shadow mode, and the mock
adapter for every system, whatever config/hotel.yaml says. Runs against its
own database (`data/demo/demo.db`) so running it twice always shows the same
picture and never touches `data/agent.db` (that is `make run`'s file). All
three sub-agents are force-enabled for this walkthrough only, so a fresh
clone sees every loop without editing config first - in a real run they stay
off until you turn them on (`config/agent.yaml: subagents.*.enabled`).
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.config import ConfigError, load_settings, sub_data_dir  # noqa: E402
from core.log import summary_line  # noqa: E402
from core.store import Store, StoreError  # noqa: E402
from tools.campaign import MIGRATE_SQL  # noqa: E402
from tools.design_requests import cmd_new as _file_design_request  # noqa: E402
from tools.run import (one_pass_budget, one_pass_content, one_pass_design,
                       one_pass_performance, one_pass_suggestions)  # noqa: E402

# Fixed so the demo never depends on the real wall-clock date - fixtures/hotel
# and fixtures/inbound are all dated around this anchor. Real runs use
# date.today().
DEMO_TODAY = "2026-08-27"


class _Args:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def main() -> int:
    try:
        settings = load_settings(demo=True)
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 1
    settings.agent.setdefault("subagents", {})
    for name in ("content_creation", "brand_collateral", "marketing_performance"):
        settings.agent["subagents"].setdefault(name, {})["enabled"] = True

    demo_db = sub_data_dir("demo") / "demo.db"
    if demo_db.exists():
        demo_db.unlink()  # every `make demo` is a clean, repeatable run
    try:
        store = Store(settings, path=demo_db)
    except StoreError as exc:
        print(f"store error: {exc}", file=sys.stderr)
        return 1
    store.migrate(MIGRATE_SQL)

    print("Marketing & Social AI demo - Hotel Aurora / The Marlow House, "
         "fixtures/hotel + fixtures/inbound\n")

    print("Suggestion queue (tools/run.py):\n")
    code, stats = one_pass_suggestions(settings, store, today=DEMO_TODAY)
    if code != 0:
        print("demo: suggestions pass did not finish cleanly", file=sys.stderr)
        return 1

    print("\nBudget optimizer (tools/run.py --budget):\n")
    bcode, bstats = one_pass_budget(settings, store, provider="mock", today=DEMO_TODAY)
    if bcode != 0:
        print("demo: budget pass did not finish cleanly", file=sys.stderr)
        return 1

    # Approve one event_signal suggestion so Content Creation AI has a queued
    # brief to work from, the same "approve, the Studio brief pre-fills" flow
    # the source demonstrates.
    from core.review import approve
    event_items = store.list_items(status="pending_review", kind="suggestion", limit=50)
    event_items = [i for i in event_items if (i.payload or {}).get("category") == "event_signal"]
    if event_items:
        approve(store, event_items[0].id, note="demo: approved to seed a campaign brief")

    print("\nContent Creation AI - The Editor (tools/run.py --content):\n")
    ccode, cstats = one_pass_content(settings, store, provider="mock")
    if ccode != 0:
        print("demo: content pass did not finish cleanly", file=sys.stderr)
        return 1

    print("\nBrand & Collateral AI - The Art Director (tools/run.py --design):\n")
    _file_design_request(store, _Args(
        brief="Terrace poster for the summer regatta", kind="poster",
        property=next(iter(settings.agent_get("properties", {})), "hotel-aurora"),
        season="summer", subject="offer", audience="couples", requested_by="Front office",
        due=None))
    dcode, dstats = one_pass_design(settings, store)
    if dcode != 0:
        print("demo: design pass did not finish cleanly", file=sys.stderr)
        return 1

    print("\nMarketing Performance AI - The Attributor (tools/run.py --performance):\n")
    pcode, pstats = one_pass_performance(settings, store, today=DEMO_TODAY)
    if pcode != 0:
        print("demo: performance pass did not finish cleanly", file=sys.stderr)
        return 1

    counts = store.counts()
    waiting = sum(counts.get(s, 0) for s in ("pending_review", "needs_human"))
    print(f"\n{waiting} item(s) waiting for a person - nothing here ever auto-applies, "
         "see docs/safety.md.")
    print("Nothing was sent or posted: mode is shadow, and demo never calls "
         "ads.set_budget()/pause(), messaging.notify_staff(), or email.send() "
         "on anything but the fixtures.")
    print("Next: `make review` to see what is waiting, or read workflows/10-suggestions.md.\n")

    total_processed = (stats.get("processed", 0) + bstats.get("processed", 0)
                      + cstats.get("processed", 0) + dstats.get("processed", 0)
                      + pstats.get("processed", 0))
    demo_stats = {"processed": total_processed, "drafted": total_processed, "sent": 0}
    print(f"DEMO OK — {summary_line(demo_stats, settings.mode)}")
    store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
