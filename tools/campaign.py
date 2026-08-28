#!/usr/bin/env python3
"""tools/campaign.py - brief Content Creation AI, browse and push its drafts.

    python3 tools/campaign.py brief --subject spa --property hotel-aurora \\
        --season winter --audience couples
    python3 tools/campaign.py brief --freestyle "Winter spa push for couples"
    python3 tools/campaign.py list
    python3 tools/campaign.py show <campaign_id>
    python3 tools/campaign.py push <campaign_id> <draft_index>
    python3 tools/campaign.py variations <campaign_id> <draft_index>

Campaigns and their drafts live in their own tables (`campaigns`,
`creative_drafts`), not the review queue - "Push to library" is a direct
human action, not an approve/reject decision, and never talks to a live ad
platform (docs/how-it-works.md "Design decisions" #3). Only a budget change
that would actually spend money goes through `core.review`'s write guard.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.config import ConfigError, load_settings  # noqa: E402
from core.store import Store, utcnow  # noqa: E402
from tools import ingest  # noqa: E402
from tools.content_engine import (Brief, CampaignResult, campaign_name, generate_campaign,
                                  generate_variations, parse_freestyle, pick_photos)  # noqa: E402

MIGRATE_SQL = """
CREATE TABLE IF NOT EXISTS campaigns (
  id          TEXT PRIMARY KEY,
  name        TEXT NOT NULL,
  brief_json  TEXT NOT NULL,
  thinking_json TEXT,
  sequence_json TEXT,
  narrative   TEXT,
  source_item TEXT,
  needs_human INTEGER NOT NULL DEFAULT 0,
  flag_reason TEXT,
  created_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS creative_drafts (
  id          TEXT PRIMARY KEY,
  campaign_id TEXT NOT NULL,
  idx         INTEGER NOT NULL,
  label       TEXT NOT NULL,
  spec_json   TEXT NOT NULL,
  off_brand   INTEGER NOT NULL DEFAULT 0,
  status      TEXT NOT NULL DEFAULT 'generated',
  created_at  TEXT NOT NULL
);
"""


def save_campaign(store: Store, name: str, brief: Brief, result: CampaignResult,
                  source_suggestion: str | None = None) -> str:
    campaign_id = uuid.uuid4().hex
    store.db.execute(
        "INSERT INTO campaigns (id, name, brief_json, thinking_json, sequence_json, "
        "source_item, needs_human, flag_reason, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (campaign_id, name, json.dumps(brief.__dict__), json.dumps(result.thinking_log),
         json.dumps(result.sequence.__dict__), source_suggestion,
         1 if result.needs_human else 0,
         " ".join(result.needs_human_reasons) or None, utcnow()))
    for i, creative in enumerate(result.creatives):
        store.db.execute(
            "INSERT INTO creative_drafts (id, campaign_id, idx, label, spec_json, "
            "off_brand, status, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (uuid.uuid4().hex, campaign_id, i, creative.label, json.dumps(creative.__dict__),
             1 if creative.off_brand else 0, "generated", utcnow()))
    return campaign_id


def generate_for_brief(store: Store, brief: Brief, content_assets: list[dict], rules: dict,
                       property_label: str, source_suggestion: str | None = None,
                       hotel_languages: tuple[str, ...] = ("en",)
                       ) -> tuple[str, CampaignResult]:
    photos = pick_photos(content_assets, brief)
    result = generate_campaign(brief, photos, rules, property_label, hotel_languages)
    name = campaign_name(brief, property_label)
    campaign_id = save_campaign(store, name, brief, result, source_suggestion)
    return campaign_id, result


def file_content_flag(store: Store, campaign_id: str, brief: Brief,
                      result: CampaignResult) -> str | None:
    """When `generate_campaign()` flags a brief (ambiguous subject, or a
    caption-language gap - see `CampaignResult.needs_human`), file a
    `suggestion`-kind item so it lands in `make review` / `tools/review.py
    list` as `needs_human` - never just a console line that scrolls away.
    Reuses the existing `suggestion` kind rather than adding a sixth kind to
    the queue; approving it means "seen it, handled it" (translated the
    captions, confirmed the subject), rejecting it discards the note.
    Returns the item id, or None when nothing was flagged.
    """
    if not result.needs_human:
        return None
    payload = {
        "category": "content_review",
        "title": f"Confirm campaign {campaign_id} before using it",
        "rationale": " ".join(result.needs_human_reasons),
        "impact": "", "evidence": [],
        "prefilled_brief": brief.freestyle, "campaign_id": campaign_id,
    }
    item, created = store.upsert_unique("suggestion", f"content-flag-{campaign_id}",
                                        payload, source="content_engine")
    if created:
        store.set_fields(item.id, draft=payload)
        store.transition(item.id, "needs_human", "agent",
                         {"reason": payload["rationale"], "campaign_id": campaign_id})
    return item.id


def cmd_brief(store: Store, settings, args) -> int:
    properties = settings.agent_get("properties", {})
    default_property = next(iter(properties), "")
    if args.freestyle:
        keywords = {slug: p.get("name", slug).lower() for slug, p in properties.items()}
        brief = parse_freestyle(args.freestyle, keywords, default_property)
    else:
        if not (args.subject and args.property and args.season and args.audience):
            print("error: give --freestyle, or all four of --subject --property "
                 "--season --audience", file=sys.stderr)
            return 2
        brief = Brief(subject=args.subject, property_slug=args.property, season=args.season,
                      audience=args.audience)
    content_assets = ingest.load_content_assets()
    property_label = properties.get(brief.property_slug, {}).get("name", brief.property_slug)
    campaign_id, result = generate_for_brief(
        store, brief, content_assets, settings.agent_get("rules", {}), property_label,
        hotel_languages=tuple(settings.hotel.languages))
    for line in result.thinking_log:
        print(f"  - {line}")
    print(f"\ncampaign {campaign_id}: {len(result.creatives)} creative(s), "
         f"{len(result.sequence.shots)}-shot video plan.")
    if result.needs_human:
        flag_id = file_content_flag(store, campaign_id, brief, result)
        print(f"\nneeds a human: {' '.join(result.needs_human_reasons)}")
        print(f"Filed as {flag_id} - see `make review` / `python3 tools/review.py list` "
             "(needs_human).")
    print(f"Run `python3 tools/campaign.py show {campaign_id}` to see the drafts, or "
         f"`python3 tools/campaign.py push {campaign_id} <index>` to push one to the library.")
    return 0


def cmd_list(store: Store, args) -> int:
    rows = store.db.execute(
        "SELECT id, name, needs_human, created_at FROM campaigns "
        "ORDER BY created_at DESC LIMIT ?", (args.limit,)).fetchall()
    if not rows:
        print("No campaigns yet. Run `python3 tools/campaign.py brief ...` first.")
        return 0
    for r in rows:
        n = store.db.execute("SELECT COUNT(*) AS n FROM creative_drafts WHERE campaign_id=?",
                             (r["id"],)).fetchone()["n"]
        flag = "  [needs_human]" if r["needs_human"] else ""
        print(f"  {r['id']}  {r['created_at']}  {r['name']}  ({n} drafts){flag}")
    return 0


def cmd_show(store: Store, args) -> int:
    row = store.db.execute("SELECT * FROM campaigns WHERE id=?", (args.id,)).fetchone()
    if row is None:
        print(f"error: no campaign {args.id}", file=sys.stderr)
        return 1
    drafts = store.db.execute(
        "SELECT idx, label, status, off_brand, spec_json FROM creative_drafts "
        "WHERE campaign_id=? ORDER BY idx", (args.id,)).fetchall()
    out = {"id": row["id"], "name": row["name"], "brief": json.loads(row["brief_json"]),
          "thinking": json.loads(row["thinking_json"] or "[]"),
          "sequence": json.loads(row["sequence_json"] or "{}"),
          "needs_human": bool(row["needs_human"]), "flag_reason": row["flag_reason"],
          "drafts": [{"idx": d["idx"], "label": d["label"], "status": d["status"],
                     "off_brand": bool(d["off_brand"]),
                     "spec": json.loads(d["spec_json"])} for d in drafts]}
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


def cmd_push(store: Store, args) -> int:
    row = store.db.execute(
        "SELECT id, status, spec_json, label FROM creative_drafts WHERE campaign_id=? AND idx=?",
        (args.campaign_id, args.index)).fetchone()
    if row is None:
        print(f"error: no draft at index {args.index} in campaign {args.campaign_id}",
             file=sys.stderr)
        return 1
    store.db.execute("UPDATE creative_drafts SET status='pushed' WHERE id=?", (row["id"],))
    store.record_event(None, "human", "pushed_draft",
                       {"campaign_id": args.campaign_id, "index": args.index})
    spec = json.loads(row["spec_json"])
    print(f"pushed \"{spec['headline']}\" to the creative library as a draft ad. "
         "A human still needs to launch it in Meta/Google Ads Manager.")
    return 0


def cmd_variations(store: Store, settings, args) -> int:
    row = store.db.execute(
        "SELECT spec_json FROM creative_drafts WHERE campaign_id=? AND idx=?",
        (args.campaign_id, args.index)).fetchone()
    if row is None:
        print(f"error: no draft at index {args.index} in campaign {args.campaign_id}",
             file=sys.stderr)
        return 1
    from tools.content_engine import CreativeSpec
    base = CreativeSpec(**json.loads(row["spec_json"]))
    content_assets = ingest.load_content_assets()
    result = generate_variations(base, content_assets, settings.agent_get("rules", {}))
    for line in result.thinking_log:
        print(f"  - {line}")
    var_campaign_id = uuid.uuid4().hex
    store.db.execute(
        "INSERT INTO campaigns (id, name, brief_json, thinking_json, sequence_json, "
        "source_item, created_at) VALUES (?,?,?,?,?,?,?)",
        (var_campaign_id, f"Variations of {base.label}", json.dumps({}),
         json.dumps(result.thinking_log), json.dumps({}), args.campaign_id, utcnow()))
    for i, creative in enumerate(result.drafts):
        store.db.execute(
            "INSERT INTO creative_drafts (id, campaign_id, idx, label, spec_json, "
            "off_brand, status, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (uuid.uuid4().hex, var_campaign_id, i, creative.label, json.dumps(creative.__dict__),
             1 if creative.off_brand else 0, "generated", utcnow()))
    print(f"\n{len(result.drafts)} variation(s) saved as campaign {var_campaign_id}.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    p_brief = sub.add_parser("brief", help="generate 12 creatives + a video plan")
    p_brief.add_argument("--freestyle", default=None)
    p_brief.add_argument("--subject", choices=["spa", "rooms", "dining", "offer"])
    p_brief.add_argument("--property", dest="property")
    p_brief.add_argument("--season", choices=["winter", "summer", "autumn", "spring"])
    p_brief.add_argument("--audience", choices=["couples", "families", "business", "wellness"])

    p_list = sub.add_parser("list", help="every generated campaign")
    p_list.add_argument("--limit", type=int, default=20)

    p_show = sub.add_parser("show", help="full detail for one campaign")
    p_show.add_argument("id")

    p_push = sub.add_parser("push", help="push one draft into the creative library")
    p_push.add_argument("campaign_id")
    p_push.add_argument("index", type=int)

    p_var = sub.add_parser("variations", help="generate variations from one draft")
    p_var.add_argument("campaign_id")
    p_var.add_argument("index", type=int)

    args = parser.parse_args(argv)
    try:
        settings = load_settings()
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 1
    store = Store(settings)
    store.migrate(MIGRATE_SQL)
    try:
        if args.command == "brief":
            return cmd_brief(store, settings, args)
        if args.command == "list":
            return cmd_list(store, args)
        if args.command == "show":
            return cmd_show(store, args)
        if args.command == "push":
            return cmd_push(store, args)
        if args.command == "variations":
            return cmd_variations(store, settings, args)
        parser.error(f"unknown command {args.command}")
        return 2
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
