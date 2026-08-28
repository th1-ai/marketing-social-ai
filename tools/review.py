#!/usr/bin/env python3
"""tools/review.py - work the review queue: list / show / approve / edit / reject / send.

    python3 tools/review.py list [--status pending_review] [--kind budget_change]
    python3 tools/review.py show <id>
    python3 tools/review.py approve <id> [--note "..."]
    python3 tools/review.py edit <id> --field-file draft.json [--note "..."]
    python3 tools/review.py reject <id> --reason "too aggressive"
    python3 tools/review.py retry <id>          # re-queue a failed send
    python3 tools/review.py send                # act on everything approved/edited
    python3 tools/review.py stale                # go-live step

One queue, five kinds of item: `suggestion`, `budget_change`, `design_request`,
`roas_alert`, `exec_report`. `send` dispatches by kind (see `_dispatch`
below) - a budget change calls the ads adapter, a ROAS alert notifies staff,
an exec report emails the manager contact, a suggestion or a design request
has nothing left to transmit: approval already is the decision, so it just
closes out. Only this tool writes `approved` / `edited` / `rejected`
(core/review.py). Only `send` writes `sending` / `sent`. Nothing here
bypasses `mode: shadow` - see docs/safety.md.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.adapters import get_email, get_messaging  # noqa: E402
from core.config import ConfigError, load_settings  # noqa: E402
from core.review import (WriteBlocked, approve, edit, list_queue, reject, retry,  # noqa: E402
                         show, stale_backlog)
from core.store import Store, StoreError  # noqa: E402
from tools.ads_adapters import get_ads  # noqa: E402


def _print_item_line(item) -> None:
    payload = item.payload or {}
    title = payload.get("title") or payload.get("asset_slug") or payload.get("brief", "")
    marker = "  [SAMPLE DATA]" if item.is_sample else ""
    print(f"  {item.id}  {item.review_status:<14} {item.kind:<14} "
          f"{str(title)[:48]}{marker}".rstrip())


def cmd_list(store, args) -> int:
    items = list_queue(store, status=args.status, kind=args.kind, limit=args.limit)
    if not items:
        print("Nothing is waiting for you.")
        return 0
    print(f"{len(items)} item(s) waiting:\n")
    for item in items:
        _print_item_line(item)
    if any(item.is_sample for item in items):
        print("\n[SAMPLE DATA] One or more items above were built from the shipped sample "
              "fixtures, not your property - the system they came from is still on the "
              "'mock' adapter. Connect it in config/hotel.yaml (docs/integrations.md) "
              "before approving them.")
    print("\nRun `python3 tools/review.py show <id>` for the full draft.")
    return 0


def cmd_show(store, args) -> int:
    try:
        detail = show(store, args.id)
    except KeyError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    payload = (detail.get("item") or {}).get("payload") or {}
    if payload.get("_sample"):
        print("[SAMPLE DATA] This item was built from the shipped sample fixtures, not your "
              "property - the system it came from is still on the 'mock' adapter. Connect it "
              "in config/hotel.yaml (docs/integrations.md) before approving it.\n")
    print(json.dumps(detail, indent=2, ensure_ascii=False, default=str))
    return 0


def cmd_approve(store, args) -> int:
    item = approve(store, args.id, note=args.note or "")
    print(f"approved {item.id} - now in the send queue")
    return 0


def cmd_edit(store, args) -> int:
    item = store.get_item(args.id)
    if item is None:
        print(f"error: no item {args.id}", file=sys.stderr)
        return 1
    fields = json.loads(Path(args.field_file).read_text(encoding="utf-8"))
    new_draft = {**(item.draft or {}), **fields}
    edit(store, args.id, new_draft, note=args.note or "")
    print(f"edited {item.id} - now in the send queue")
    return 0


def cmd_reject(store, args) -> int:
    item = reject(store, args.id, reason=args.reason or "")
    print(f"rejected {item.id}")
    return 0


def cmd_retry(store, args) -> int:
    item = retry(store, args.id)
    print(f"queued {item.id} for another send attempt")
    return 0


def _dispatch(settings, store, item):
    """Perform the real action for one claimed item, by kind. Returns a
    message id (or None) on success; raises WriteBlocked or a real error."""
    payload = item.payload or {}
    if item.kind == "budget_change":
        ads = get_ads(settings)
        action = payload.get("action")
        if action == "pause":
            result = ads.pause(payload["asset_slug"], item=item)
        else:
            result = ads.set_budget(payload["asset_slug"], payload["to_daily"], item=item)
        return result.get("message_id")
    if item.kind == "roas_alert":
        messaging = get_messaging(settings)
        result = messaging.notify_staff(payload.get("reason", "ROAS drop"), item=item)
        return result.get("message_id")
    if item.kind == "exec_report":
        email = get_email(settings)
        result = email.send(payload["to"], payload["subject"], payload["body"], item=item)
        return result.get("message_id")
    # suggestion / design_request: approval IS the action - nothing external to send.
    return None


def cmd_send(store, settings, args) -> int:
    claimed = store.claim_for_send(limit=args.limit)
    if not claimed:
        print("Nothing approved or edited is waiting to send.")
        return 0
    sent, blocked, failed = 0, 0, 0
    for item in claimed:
        try:
            message_id = _dispatch(settings, store, item)
        except WriteBlocked as exc:
            # Not a failure: the mode blocked it. The approval stands for go-live.
            store.transition(item.id, "approved", "agent", {"blocked": str(exc)[:200]})
            print(f"blocked {item.id} (approval kept): {exc}")
            blocked += 1
            continue
        except Exception as exc:  # noqa: BLE001 - record and move on, never crash the batch
            store.mark_send_failed(item.id, str(exc))
            print(f"failed {item.id}: {exc}")
            failed += 1
            continue
        store.mark_sent(item.id, message_id)
        print(f"done {item.id} ({item.kind})")
        sent += 1
    print(f"\n{sent} done, {blocked} blocked (approval kept), {failed} failed.")
    return 0 if failed == 0 and blocked == 0 else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="what is waiting for a human")
    p_list.add_argument("--status", default=None)
    p_list.add_argument("--kind", default=None,
                        help="suggestion | budget_change | design_request | roas_alert")
    p_list.add_argument("--limit", type=int, default=50)

    p_show = sub.add_parser("show", help="full detail for one item")
    p_show.add_argument("id")

    p_approve = sub.add_parser("approve", help="approve the draft unchanged")
    p_approve.add_argument("id")
    p_approve.add_argument("--note", default="")

    p_edit = sub.add_parser("edit", help="rewrite fields (json), then queue it")
    p_edit.add_argument("id")
    p_edit.add_argument("--field-file", required=True,
                        help="a JSON file of {field: new_value} to merge into the draft")
    p_edit.add_argument("--note", default="")

    p_reject = sub.add_parser("reject", help="discard the draft")
    p_reject.add_argument("id")
    p_reject.add_argument("--reason", "--note", dest="reason", default="")

    p_retry = sub.add_parser("retry", help="re-queue a failed send")
    p_retry.add_argument("id")

    p_send = sub.add_parser("send", help="act on everything approved or edited")
    p_send.add_argument("--limit", type=int, default=20)

    sub.add_parser("stale", help="go-live step: mark everything still un-actioned as stale "
                                 "(the shadow-era queue never went out and is out of date)")

    args = parser.parse_args(argv)

    try:
        settings = load_settings()
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 1

    store = Store(settings)
    try:
        if args.command == "list":
            return cmd_list(store, args)
        if args.command == "show":
            return cmd_show(store, args)
        if args.command == "approve":
            return cmd_approve(store, args)
        if args.command == "edit":
            return cmd_edit(store, args)
        if args.command == "reject":
            return cmd_reject(store, args)
        if args.command == "retry":
            return cmd_retry(store, args)
        if args.command == "send":
            return cmd_send(store, settings, args)
        if args.command == "stale":
            moved = stale_backlog(store)
            print(f"marked {len(moved)} item(s) stale. Nothing from before go-live will send.")
            return 0
        parser.error(f"unknown command {args.command}")
        return 2
    except StoreError as exc:
        print(f"cannot do that: {exc}", file=sys.stderr)
        return 1
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
