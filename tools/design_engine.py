"""tools/design_engine.py - Brand & Collateral AI's design-request queue.

The source has no design-request queue at all (specs/brand-collateral-ai.md
"Open questions" #1: "Design it: a design_requests table with requested_by /
brief / due / status ... would be the honest v1"). This module is that v1:
a plain function that drafts one open request against the brand kit, reusing
`tools/content_engine.py`'s photo scoring so a menu or a poster is picked
from the same rights-cleared library the Editor composes from.

Pure function: no I/O, no LLM. `tools/run.py --design` is the only place
that writes a draft back to the store.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from tools.content_engine import Brief, CreativeSpec, LAYOUTS, campaign_name, pick_photos

COLLATERAL_LAYOUTS = {
    "social": "center", "poster": "bottom", "menu": "panel", "offer_graphic": "bottom",
}


@dataclass
class DesignDraft:
    kind: str  # social | poster | menu | offer_graphic
    title: str
    creative: CreativeSpec | None
    notes: str
    thinking_log: list[str] = field(default_factory=list)


def draft_design_request(request: dict, content_assets: list[dict], rules: dict,
                         property_label: str) -> DesignDraft:
    """``request``: {brief, kind, property_slug, season, subject, audience}."""
    kind = request.get("kind", "social")
    brief = Brief(subject=request.get("subject", "offer"),
                 property_slug=request.get("property_slug", ""),
                 season=request.get("season", "summer"),
                 audience=request.get("audience", "couples"), freestyle=request.get("brief", ""))
    photos = pick_photos(content_assets, brief, limit=1)
    log = [f"Read the request: \"{request.get('brief', '')[:80]}\".",
          f"Matched collateral type '{kind}' to the {COLLATERAL_LAYOUTS.get(kind, 'bottom')} "
          f"layout.", "Checked the brand kit for a photo and a colourway."]
    if not photos:
        log.append("No photo in the library matched this brief closely enough.")
        return DesignDraft(kind=kind, title=campaign_name(brief, property_label),
                           creative=None,
                           notes="The photo library did not return a strong match - "
                                "a designer will need to pick the shot by hand.",
                           thinking_log=log)
    photo = photos[0]
    guard = rules.get("brand_guard", True)
    name_property = rules.get("always_name_property", True)
    cta_color = "#1379A8" if guard else "#D6188F"
    creative = CreativeSpec(
        photo_slug=photo["slug"], photo_url=photo.get("url", ""),
        layout=COLLATERAL_LAYOUTS.get(kind, "bottom"), treatment="none",
        headline=campaign_name(brief, property_label), subline=request.get("brief", "")[:90],
        cta="See details", cta_color=cta_color,
        text_tone="dark" if COLLATERAL_LAYOUTS.get(kind, "bottom") == "panel" else "light",
        property_slug=brief.property_slug, eyebrow=property_label if name_property else "",
        off_brand=not guard, label=f"{kind} draft for {photo.get('title', photo['slug'])}",
    )
    log.append(f"Drafted the {kind} against \"{photo.get('title', photo['slug'])}\".")
    notes = ("On-brand." if guard else "Brand guard is off - this draft is marked off-brand; "
            "a designer must confirm the colourway before it ships.")
    return DesignDraft(kind=kind, title=creative.headline, creative=creative, notes=notes,
                       thinking_log=log)
