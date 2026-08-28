#!/usr/bin/env python3
"""tools/design_requests.py - file a request for Brand & Collateral AI.

    python3 tools/design_requests.py new --brief "Terrace poster for the derby" \\
        --kind poster --property hotel-aurora [--season summer] [--subject offer] \\
        [--requested-by "Front office"] [--due 2026-09-10]
    python3 tools/design_requests.py list [--status new]

A request sits at `new` until `tools/run.py --design` drafts it (Brand &
Collateral AI must be enabled - config/agent.yaml: subagents.brand_collateral),
then moves to `pending_review` for a designer to approve or reject in
`workflows/80-review.md`. This is the v1 of the source's promised
"design-request queue with a human approval step" - see docs/how-it-works.md
"Design decisions" #4.

`list` with no `--status` shows a freshly filed `new` request too, not just
`pending_review`/`needs_human`/`stale`/`failed` - a request should show up
in `list` the moment `new` files it, before `--design` has drafted it.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.config import ConfigError, load_settings  # noqa: E402
from core.review import ACTIONABLE_STATES, list_queue  # noqa: E402
from core.store import Store, StoreError  # noqa: E402

#: `list` with no `--status` should show a request the moment it is filed,
#: not just once `--design` has drafted it - core.review.ACTIONABLE_STATES
#: (a generic "waiting on a human" set shared by every kind in this family)
#: does not include `new`, because for most kinds `new` means "the agent
#: hasn't looked at it yet," not "a human is waiting." Here a freshly filed
#: request *is* new-but-actionable: `workflows/22-brand-collateral.md`'s own
#: worked example runs `new` immediately followed by `list` with no flag.
DEFAULT_LIST_STATES = sorted(ACTIONABLE_STATES | {"new"})


def cmd_new(store: Store, args) -> int:
    payload = {"brief": args.brief, "kind": args.kind, "property_slug": args.property,
              "season": args.season or "summer", "subject": args.subject or "offer",
              "audience": args.audience or "couples", "requested_by": args.requested_by or "",
              "due": args.due or ""}
    item = store.upsert_item("design_requests", f"dr-{store.next_sequence('design_request')}",
                             kind="design_request", payload=payload)
    print(f"filed {item.id} - kind={args.kind}, waiting for Brand & Collateral AI "
         "(`tools/run.py --design`) to draft it.")
    return 0


def cmd_list(store: Store, args) -> int:
    if args.status:
        items = list_queue(store, status=args.status, kind="design_request", limit=args.limit)
    else:
        items = store.list_items(status=DEFAULT_LIST_STATES, kind="design_request",
                                 limit=args.limit)
    if not items:
        print("No design requests waiting.")
        return 0
    print(f"{len(items)} request(s):\n")
    for item in items:
        p = item.payload or {}
        print(f"  {item.id}  {item.review_status:<14} {p.get('kind', '-'):<12} "
             f"{p.get('brief', '')[:50]}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    p_new = sub.add_parser("new", help="file a design request")
    p_new.add_argument("--brief", required=True)
    p_new.add_argument("--kind", required=True,
                       choices=["social", "poster", "menu", "offer_graphic"])
    p_new.add_argument("--property", dest="property", required=True)
    p_new.add_argument("--season", choices=["winter", "summer", "autumn", "spring"])
    p_new.add_argument("--subject", choices=["spa", "rooms", "dining", "offer"])
    p_new.add_argument("--audience", choices=["couples", "families", "business", "wellness"])
    p_new.add_argument("--requested-by", default=None)
    p_new.add_argument("--due", default=None, help="YYYY-MM-DD")

    p_list = sub.add_parser("list", help="every design request")
    p_list.add_argument("--status", default=None)
    p_list.add_argument("--limit", type=int, default=50)

    args = parser.parse_args(argv)
    try:
        settings = load_settings()
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 1
    store = Store(settings)
    try:
        if args.command == "new":
            return cmd_new(store, args)
        if args.command == "list":
            return cmd_list(store, args)
        parser.error(f"unknown command {args.command}")
        return 2
    except StoreError as exc:
        print(f"cannot do that: {exc}", file=sys.stderr)
        return 1
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
