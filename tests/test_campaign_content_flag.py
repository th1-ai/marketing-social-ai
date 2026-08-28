"""Tests for tools/campaign.py's needs_human flag - regression for
SIMULATION.md Finding 1.

A Portuguese freestyle brief used to be silently mis-mapped (subject:
"offer" instead of "rooms") and produced an all-English campaign with zero
warning. The fix: `tools/content_engine.py` recognises the same subject
concepts in five more languages and flags (never guesses) when the copy
bank can't caption the brief's own language, or when the subject truly
can't be matched. This file checks the tool layer that turns that flag into
something a human actually sees: a `suggestion`-kind item filed straight at
`needs_human`, and the `campaigns` row carrying the same flag.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.review import ACTIONABLE_STATES
from core.store import Store
from tools import ingest
from tools.campaign import MIGRATE_SQL, file_content_flag, generate_for_brief
from tools.content_engine import parse_freestyle

PROPERTIES = {"hotel-aurora": "hotel aurora, aurora"}
PORTUGUESE_BRIEF = "Preciso de um anúncio de quartos... para o verão, para casais"


def _store(tmp_path) -> Store:
    store = Store(path=tmp_path / "test.db")
    store.migrate(MIGRATE_SQL)
    return store


def test_portuguese_brief_files_a_needs_human_item(tmp_path):
    store = _store(tmp_path)
    try:
        brief = parse_freestyle(PORTUGUESE_BRIEF, PROPERTIES, "hotel-aurora")
        assert brief.subject == "rooms"  # the mis-mapping this whole fix is about

        content_assets = ingest.load_content_assets()
        campaign_id, result = generate_for_brief(
            store, brief, content_assets, {"brand_guard": True}, "Hotel Aurora",
            hotel_languages=("en", "pt"))
        assert result.needs_human is True

        flag_id = file_content_flag(store, campaign_id, brief, result)
        assert flag_id is not None

        item = store.get_item(flag_id)
        assert item is not None
        assert item.kind == "suggestion"
        assert item.review_status == "needs_human"  # never silent, never pending_review
        assert "English" in (item.payload or {}).get("rationale", "")
        assert item.payload.get("campaign_id") == campaign_id

        # `needs_human` is one of the actionable states - it must actually
        # surface in `make review` / `tools/review.py list`, not just exist.
        assert item.review_status in ACTIONABLE_STATES

        # re-running the same brief must not file a second item.
        campaign_id_2, result_2 = generate_for_brief(
            store, brief, content_assets, {"brand_guard": True}, "Hotel Aurora",
            hotel_languages=("en", "pt"))
        flag_id_2 = file_content_flag(store, campaign_id_2, brief, result_2)
        assert flag_id_2 != flag_id  # a new campaign, so a new flag item...
        # ...but re-filing the *same* campaign_id is idempotent (upsert_unique).
        flag_id_2_again = file_content_flag(store, campaign_id_2, brief, result_2)
        assert flag_id_2_again == flag_id_2
    finally:
        store.close()


def test_campaign_row_carries_the_needs_human_flag(tmp_path):
    store = _store(tmp_path)
    try:
        brief = parse_freestyle(PORTUGUESE_BRIEF, PROPERTIES, "hotel-aurora")
        content_assets = ingest.load_content_assets()
        campaign_id, result = generate_for_brief(
            store, brief, content_assets, {"brand_guard": True}, "Hotel Aurora",
            hotel_languages=("en", "pt"))
        row = store.db.execute("SELECT needs_human, flag_reason FROM campaigns WHERE id=?",
                               (campaign_id,)).fetchone()
        assert row["needs_human"] == 1
        assert "English" in row["flag_reason"]
        assert result.needs_human_reasons  # thinking_log/console text, never silent
    finally:
        store.close()


def test_english_brief_files_no_flag(tmp_path):
    store = _store(tmp_path)
    try:
        brief = parse_freestyle("Winter spa push for couples", PROPERTIES, "hotel-aurora")
        content_assets = ingest.load_content_assets()
        campaign_id, result = generate_for_brief(
            store, brief, content_assets, {"brand_guard": True}, "Hotel Aurora",
            hotel_languages=("en", "pt"))
        assert result.needs_human is False
        assert file_content_flag(store, campaign_id, brief, result) is None
        row = store.db.execute("SELECT needs_human FROM campaigns WHERE id=?",
                               (campaign_id,)).fetchone()
        assert row["needs_human"] == 0
    finally:
        store.close()
