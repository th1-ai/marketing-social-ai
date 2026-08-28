#!/usr/bin/env python3
"""tools/brand_kit.py - Brand & Collateral AI's standing constraint layer.

    python3 tools/brand_kit.py show
    python3 tools/brand_kit.py show --property hotel-aurora

Read-only, no run loop - matches the source: "the content the AI is allowed
to compose from." This is what `tools/content_engine.py` and
`tools/design_engine.py` score photos against; edit
`fixtures/hotel/content_assets.json` (or `data/imports/content_assets.json`)
to give it your own colours, fonts, logos, voice docs and photo library.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import ingest  # noqa: E402


def cmd_show(args) -> int:
    assets = ingest.load_content_assets()
    if args.property:
        assets = [a for a in assets
                 if a.get("property_slug") in (args.property, "collection", None)]

    colors = [a for a in assets if a.get("type") == "color"]
    fonts = [a for a in assets if a.get("type") == "font"]
    logos = [a for a in assets if a.get("type") == "logo"]
    voice_docs = [a for a in assets if a.get("type") == "voice_doc"]
    photos = [a for a in assets if a.get("type") == "photo"]

    print("Brand kit — the palette, type and marks every creative must respect.\n")
    print(f"Colours ({len(colors)}):")
    for c in colors:
        meta = c.get("meta", {})
        print(f"  {c['title']}  {meta.get('hex', '')}  — {meta.get('usage', '')}")
    print(f"\nTypography ({len(fonts)}):")
    for f in fonts:
        meta = f.get("meta", {})
        print(f"  {f['title']}  {meta.get('family', '')}  ({meta.get('role', '')})")
    print(f"\nLogo files ({len(logos)}):")
    for l in logos:
        print(f"  {l['title']}  tags={','.join(l.get('tags', []))}")
    if not logos:
        print("  Wordmarks render from the brand type — no logo files yet.")
    print(f"\nVoice documents ({len(voice_docs)}):")
    for d in voice_docs:
        print(f"  {d['title']}")
    print(f"\nPhoto library ({len(photos)} tagged so the AI can find "
         "'winter · spa · property' on its own):")
    for p in photos[:20]:
        star = "★ " if p.get("hero") else "  "
        print(f"  {star}{p['slug']}  [{p.get('property_slug', '-')}]  "
             f"{', '.join(p.get('tags', [])[:4])}")
    if len(photos) > 20:
        print(f"  … and {len(photos) - 20} more")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p_show = sub.add_parser("show", help="list the whole brand kit")
    p_show.add_argument("--property", default=None)
    args = parser.parse_args(argv)
    if args.command == "show":
        return cmd_show(args)
    parser.error(f"unknown command {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
