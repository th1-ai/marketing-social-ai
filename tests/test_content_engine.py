"""Tests for tools/content_engine.py - Content Creation AI's engine.

No LLM, no store: pure functions over plain dicts, per the engine's own
determinism rule (docs/how-it-works.md, "no LLM, no randomness").
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.content_engine import (Brief, CreativeSpec, detect_brief_language, generate_campaign,
                                  generate_variations, parse_freestyle, pick_photos, score_photo)

PROPERTIES = {"hotel-aurora": "hotel aurora, aurora", "marlow-house": "marlow, marlow house"}

PHOTOS = [
    {"slug": "ph-hot-tub", "type": "photo", "url": "https://example.com/a.jpg",
     "property_slug": "hotel-aurora", "tags": ["spa", "hot-tub", "snow", "winter"],
     "season": "winter", "hero": True},
    {"slug": "ph-pool", "type": "photo", "url": "https://example.com/b.jpg",
     "property_slug": "hotel-aurora", "tags": ["pool", "beach", "coast"],
     "season": "summer", "hero": False},
    {"slug": "ph-room", "type": "photo", "url": "https://example.com/c.jpg",
     "property_slug": "hotel-aurora", "tags": ["room", "suite", "bed"],
     "season": "all", "hero": False},
    {"slug": "ph-dining", "type": "photo", "url": "https://example.com/d.jpg",
     "property_slug": "hotel-aurora", "tags": ["dining", "restaurant"],
     "season": "all", "hero": False},
]


def test_parse_freestyle_maps_winter_spa_couples():
    brief = parse_freestyle("Winter spa push for couples", PROPERTIES, "hotel-aurora")
    assert brief.subject == "spa"
    assert brief.season == "winter"
    assert brief.audience == "couples"


def test_parse_freestyle_defaults_when_nothing_matches():
    brief = parse_freestyle("Something vague", PROPERTIES, "hotel-aurora")
    assert brief.subject == "offer"
    assert brief.season == "summer"
    assert brief.audience == "couples"
    assert brief.property_slug == "hotel-aurora"
    # nothing in any of the six languages matched - this was a default, not a
    # match, and a caller must be able to tell the difference (see
    # generate_campaign()'s needs_human flag, docs/how-it-works.md #13).
    assert brief.subject_confident is False
    assert brief.language == "en"


# -- Portuguese freestyle brief: regression for SIMULATION.md Finding 1 -----
# ("Preciso de um anúncio de quartos... para o verão, para casais" was
# silently mapped to subject: "offer" and produced an all-English campaign
# with zero warning). The fix: recognise the same subject concepts in
# Spanish/French/German/Italian/Portuguese too (accent-folded), and flag
# rather than guess when the copy bank can't caption the brief's language.
PORTUGUESE_BRIEF = "Preciso de um anúncio de quartos... para o verão, para casais"


def test_parse_freestyle_maps_the_portuguese_rooms_brief_correctly():
    brief = parse_freestyle(PORTUGUESE_BRIEF, PROPERTIES, "hotel-aurora")
    assert brief.subject == "rooms"  # was silently "offer" before the fix
    assert brief.subject_confident is True  # a real match, not a default
    assert brief.audience == "couples"  # "casais"
    assert brief.language == "pt"


def test_parse_freestyle_recognises_accent_folded_portuguese():
    # same brief, accents stripped by hand (a non-accented keyboard/phone) -
    # must map identically, per "accent-folded" in the fix requirement.
    folded = parse_freestyle("Preciso de um anuncio de quartos... para o verao, para casais",
                             PROPERTIES, "hotel-aurora")
    assert folded.subject == "rooms"
    assert folded.language == "pt"


def test_detect_brief_language_defaults_to_english():
    assert detect_brief_language("Winter spa push for couples") == "en"
    assert detect_brief_language("Something vague") == "en"


def test_generate_campaign_flags_needs_human_when_hotel_speaks_the_brief_language():
    brief = parse_freestyle(PORTUGUESE_BRIEF, PROPERTIES, "hotel-aurora")
    photos = pick_photos(PHOTOS, brief)
    result = generate_campaign(brief, photos, {"brand_guard": True}, "Hotel Aurora",
                               hotel_languages=("en", "pt"))
    assert result.needs_human is True
    assert any("English" in r and "Portuguese" in r for r in result.needs_human_reasons)
    # never silent: the flag is in the console-facing thinking log too.
    assert any("Flagged for a human" in line for line in result.thinking_log)
    # still drafted, not blocked - a human gets a head start, not nothing.
    assert len(result.creatives) == 12


def test_generate_campaign_does_not_flag_a_language_the_hotel_does_not_speak():
    brief = parse_freestyle(PORTUGUESE_BRIEF, PROPERTIES, "hotel-aurora")
    photos = pick_photos(PHOTOS, brief)
    # hotel_languages defaults to ("en",) - Portuguese is not one of them.
    result = generate_campaign(brief, photos, {"brand_guard": True}, "Hotel Aurora")
    assert result.needs_human is False
    assert result.needs_human_reasons == []


def test_generate_campaign_flags_needs_human_for_an_unconfident_subject():
    brief = parse_freestyle("Something vague", PROPERTIES, "hotel-aurora")
    photos = pick_photos(PHOTOS, brief)
    result = generate_campaign(brief, photos, {"brand_guard": True}, "Hotel Aurora")
    assert result.needs_human is True
    assert any("could not confidently tell" in r.lower() for r in result.needs_human_reasons)


def test_score_photo_rewards_property_subject_and_season_match():
    brief = Brief(subject="spa", property_slug="hotel-aurora", season="winter",
                 audience="couples")
    hot_tub_score = score_photo(PHOTOS[0], brief)
    pool_score = score_photo(PHOTOS[1], brief)
    assert hot_tub_score > pool_score  # matches property + subject + season + hero


def test_score_photo_penalises_the_wrong_season():
    # tags stripped from both so only the property/season/hero terms are in play -
    # a subject-tag hit would otherwise swamp the -3 season penalty being tested.
    winter_brief = Brief(subject="offer", property_slug="hotel-aurora", season="winter",
                         audience="couples")
    summer_photo = {**PHOTOS[1], "tags": [], "season": "summer"}
    winter_photo = {**PHOTOS[0], "tags": [], "season": "winter"}
    assert score_photo(winter_photo, winter_brief) > score_photo(summer_photo, winter_brief)


def test_pick_photos_orders_by_score_then_ties_broken_by_slug():
    brief = Brief(subject="offer", property_slug="hotel-aurora", season="summer",
                 audience="couples")
    picks = pick_photos(PHOTOS, brief, limit=4)
    # ph-room and ph-dining score equal (4) - "ph-dining" sorts before "ph-room"
    assert [p["slug"] for p in picks] == ["ph-pool", "ph-dining", "ph-room", "ph-hot-tub"]


def test_generate_campaign_produces_twelve_creatives():
    brief = Brief(subject="spa", property_slug="hotel-aurora", season="winter",
                 audience="couples")
    photos = pick_photos(PHOTOS, brief)
    result = generate_campaign(brief, photos, {"brand_guard": True}, "Hotel Aurora")
    assert len(result.creatives) == 12
    assert all(not c.off_brand for c in result.creatives)  # brand guard on


def test_generate_campaign_is_deterministic():
    brief = Brief(subject="spa", property_slug="hotel-aurora", season="winter",
                 audience="couples")
    photos = pick_photos(PHOTOS, brief)
    a = generate_campaign(brief, photos, {"brand_guard": True}, "Hotel Aurora")
    b = generate_campaign(brief, photos, {"brand_guard": True}, "Hotel Aurora")
    assert [c.__dict__ for c in a.creatives] == [c.__dict__ for c in b.creatives]


def test_brand_guard_off_marks_every_fourth_draft_off_brand():
    brief = Brief(subject="offer", property_slug="hotel-aurora", season="summer",
                 audience="couples")
    photos = pick_photos(PHOTOS, brief)
    result = generate_campaign(brief, photos, {"brand_guard": False}, "Hotel Aurora")
    off_brand_indexes = [i for i, c in enumerate(result.creatives) if c.off_brand]
    assert off_brand_indexes == [3, 7, 11]


def test_always_name_property_off_drops_the_eyebrow():
    brief = Brief(subject="offer", property_slug="hotel-aurora", season="summer",
                 audience="couples")
    photos = pick_photos(PHOTOS, brief)
    result = generate_campaign(brief, photos, {"always_name_property": False}, "Hotel Aurora")
    assert all(c.eyebrow == "" for c in result.creatives)


def test_variation_cap_returns_eleven_images_plus_the_video():
    base = CreativeSpec(photo_slug="ph-hot-tub", photo_url="https://example.com/a.jpg",
                        layout="bottom", treatment="none", headline="Apres, then relax",
                        subline="test", cta="Book the winter escape", cta_color="#1379A8",
                        text_tone="light", property_slug="hotel-aurora", label="base")
    result = generate_variations(base, PHOTOS, {"variation_cap": True})
    assert len(result.drafts) <= 11


def test_variation_cap_off_allows_the_full_run():
    base = CreativeSpec(photo_slug="ph-hot-tub", photo_url="https://example.com/a.jpg",
                        layout="bottom", treatment="none", headline="Apres, then relax",
                        subline="test", cta="Book the winter escape", cta_color="#1379A8",
                        text_tone="light", property_slug="hotel-aurora", label="base")
    capped = generate_variations(base, PHOTOS, {"variation_cap": True})
    uncapped = generate_variations(base, PHOTOS, {"variation_cap": False})
    assert len(uncapped.drafts) >= len(capped.drafts)
