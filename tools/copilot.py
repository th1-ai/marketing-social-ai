#!/usr/bin/env python3
"""tools/copilot.py - the marketing copilot: one grounded question, one answer.

    python3 tools/copilot.py ask "Which creative should I put more money behind?"
    python3 tools/copilot.py ask "..." --provider mock

Builds a compact, factual context from the same 30-day ad-performance
aggregates the budget desk reads (never invented numbers - "DATA
TRUTHFULNESS: only state numbers that come from your tools", ported from
the source's own system prompt) and asks one schema-constrained question.
Simpler than the source's six-tool loop (docs/how-it-works.md "Design
decisions" #9) but the same idea: grounded facts in, one answer out, and it
can file a suggestion into the queue when it lands on something concrete.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.config import ConfigError, load_settings  # noqa: E402
from core.llm import LLMError, LLMPendingInteractive, complete  # noqa: E402
from core.store import Store, StoreError  # noqa: E402
from core.templates import build_prompt  # noqa: E402
from tools import ingest  # noqa: E402


def _context(as_of: str | None = None) -> str:
    perf = ingest.load_ad_performance()
    assets = {a["slug"]: a for a in ingest.load_marketing_assets()}
    slugs = sorted({r["asset_slug"] for r in perf})
    lines = ["asset_slug | headline | 30d spend | 30d revenue | 30d ROAS | 30d CTR%"]
    for slug in slugs:
        agg = ingest.aggregate_30d(perf, slug, as_of=as_of)
        headline = assets.get(slug, {}).get("headline", slug)
        lines.append(f"{slug} | {headline} | €{agg['spend']} | €{agg['revenue']} | "
                    f"{agg['roas']}x | {agg['ctr_pct']}%")
    return "\n".join(lines)


def cmd_ask(args) -> int:
    try:
        settings = load_settings(provider=args.provider)
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 1
    store = Store(settings)
    schema = json.loads((REPO_ROOT / "prompts" / "schemas" / "copilot_ask.json")
                        .read_text(encoding="utf-8"))
    prompt = build_prompt("copilot_ask", settings=settings, item={"question": args.question},
                          context=_context(), fixture_id=args.fixture_id)
    try:
        result = complete("copilot_ask", prompt, schema, settings=settings,
                          provider=args.provider, store=store, fixture_id=args.fixture_id)
    except LLMPendingInteractive as exc:
        print(str(exc))
        store.close()
        return 3
    except LLMError as exc:
        print(f"error: {exc}", file=sys.stderr)
        store.close()
        return 1
    data = result.data or {}
    print(data.get("reply_markdown", ""))
    suggestion = data.get("suggested_suggestion")
    if suggestion:
        slug = f"sg-chat-{store.next_sequence('copilot_suggestion')}"
        payload = {"category": suggestion.get("category", "budget_shift"),
                  "title": suggestion.get("title", ""), "rationale": suggestion.get("rationale", ""),
                  "impact": suggestion.get("impact", ""),
                  "evidence": [{"type": "metric", "ref": "chat", "label": suggestion.get("title", "")}]}
        item, created = store.upsert_unique("suggestion", slug, payload, source="copilot")
        if created:
            store.set_fields(item.id, draft=payload)
            store.transition(item.id, "dispatched", "agent")
            store.transition(item.id, "pending_review", "agent")
            print(f"\nFiled a suggestion: {item.id} — \"{payload['title']}\"")
    store.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p_ask = sub.add_parser("ask", help="ask the marketing copilot a question")
    p_ask.add_argument("question")
    p_ask.add_argument("--provider", default=None)
    p_ask.add_argument("--fixture-id", default=None,
                       help="which fixtures/expected/copilot_ask/<id>.json to use "
                           "with --provider mock")
    args = parser.parse_args(argv)
    if args.command == "ask":
        return cmd_ask(args)
    parser.error(f"unknown command {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
