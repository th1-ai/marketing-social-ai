"""Tests for tools/design_engine.py - Brand & Collateral AI's draft function."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.design_engine import draft_design_request

CONTENT_ASSETS = [
    {"slug": "ph-terrace", "type": "photo", "url": "https://example.com/terrace.jpg",
     "property_slug": "hotel-aurora", "tags": ["dining", "terrace", "breakfast"],
     "season": "summer", "hero": True, "title": "Terrace"},
]
RULES_ON = {"brand_guard": True, "always_name_property": True}
RULES_OFF = {"brand_guard": False, "always_name_property": False}


def test_draft_design_request_picks_a_matching_photo():
    request = {"brief": "Terrace poster for the derby", "kind": "poster",
              "property_slug": "hotel-aurora", "season": "summer", "subject": "dining",
              "audience": "couples"}
    draft = draft_design_request(request, CONTENT_ASSETS, RULES_ON, "Hotel Aurora")
    assert draft.creative is not None
    assert draft.creative.photo_slug == "ph-terrace"
    assert draft.creative.layout == "bottom"  # kind=poster -> COLLATERAL_LAYOUTS["poster"]
    assert draft.creative.off_brand is False


def test_draft_design_request_flags_off_brand_when_guard_is_off():
    request = {"brief": "Terrace poster", "kind": "poster", "property_slug": "hotel-aurora",
              "season": "summer", "subject": "dining", "audience": "couples"}
    draft = draft_design_request(request, CONTENT_ASSETS, RULES_OFF, "Hotel Aurora")
    assert draft.creative.off_brand is True
    assert "off" in draft.notes.lower()


def test_draft_design_request_handles_no_photo_match_gracefully():
    request = {"brief": "Spa retreat flyer", "kind": "social", "property_slug": "hotel-aurora",
              "season": "winter", "subject": "spa", "audience": "wellness"}
    draft = draft_design_request(request, [], RULES_ON, "Hotel Aurora")
    assert draft.creative is None
    assert "designer" in draft.notes.lower()
