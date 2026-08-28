"""Integration tests: the bundled fixtures, through tools/run.py's real
functions, with provider=mock and a throwaway store. No network, no
credentials - the same path `make demo` and a real overnight run both take.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.config import load_settings
from core.review import approve
from core.store import Store
from tools.campaign import MIGRATE_SQL
from tools.run import one_pass_budget, one_pass_design, one_pass_suggestions

TODAY = "2026-08-27"


def _store(tmp_path, monkeypatch, *, provider="mock", mode=None):
    """Isolated settings: a real `config/agent.yaml` (a hotel's own twin pairs,
    once they have set some up) must never change what these tests exercise -
    see build-repo.md and docs/how-it-works.md "Tests never read the live
    config." AGENT_CONFIG_DIR points load_settings() at fresh copies of the
    shipped examples instead.
    """
    monkeypatch.chdir(REPO_ROOT)
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir()
    hotel_yaml = (REPO_ROOT / "config" / "hotel.example.yaml").read_text(encoding="utf-8")
    if mode == "live":
        hotel_yaml = hotel_yaml.replace("mode: shadow", "mode: live")
    (cfg_dir / "hotel.yaml").write_text(hotel_yaml, encoding="utf-8")
    (cfg_dir / "agent.yaml").write_text(
        (REPO_ROOT / "config" / "agent.example.yaml").read_text(encoding="utf-8"),
        encoding="utf-8")
    monkeypatch.setenv("AGENT_CONFIG_DIR", str(cfg_dir))
    settings = load_settings(provider=provider)
    store = Store(settings, path=tmp_path / "test.db")
    store.migrate(MIGRATE_SQL)
    return settings, store


def test_suggestions_pass_produces_items_on_the_fixtures(tmp_path, monkeypatch):
    settings, store = _store(tmp_path, monkeypatch)
    code, stats = one_pass_suggestions(settings, store, today=TODAY)
    store.close()
    assert code == 0
    assert stats["processed"] > 0
    assert stats["pending_review"] > 0


def test_suggestions_pass_is_idempotent_on_a_second_run(tmp_path, monkeypatch):
    settings, store = _store(tmp_path, monkeypatch)
    one_pass_suggestions(settings, store, today=TODAY)
    first_total = sum(store.counts().values())
    code, stats = one_pass_suggestions(settings, store, today=TODAY)
    second_total = sum(store.counts().values())
    store.close()
    assert code == 0
    assert stats["processed"] == 0  # everything already exists -> all skipped
    assert stats["skipped"] > 0
    assert second_total == first_total  # no duplicate rows on the re-run


def test_budget_pass_never_writes_a_budget_change_to_auto_sent(tmp_path, monkeypatch):
    settings, store = _store(tmp_path, monkeypatch)
    code, stats = one_pass_budget(settings, store, provider="mock", today=TODAY)
    counts = store.counts()
    store.close()
    assert code == 0
    assert stats["pending_review"] > 0
    assert counts.get("auto_sent", 0) == 0  # docs/how-it-works.md design decision #12


def test_shadow_mode_blocks_an_approved_budget_change_from_sending(tmp_path, monkeypatch):
    from core.review import WriteBlocked, assert_write_allowed
    settings, store = _store(tmp_path, monkeypatch)
    one_pass_budget(settings, store, provider="mock", today=TODAY)
    items = store.list_items(status="pending_review", kind="budget_change", limit=5)
    assert items
    approved = approve(store, items[0].id)
    assert approved.review_status == "approved"
    try:
        assert_write_allowed(settings, "apply_budget_change", approved)
        raised = False
    except WriteBlocked:
        raised = True
    store.close()
    assert raised  # shadow blocks every write, approved or not


def test_live_mode_allows_an_approved_budget_change_through_the_guard(tmp_path, monkeypatch):
    from core.review import assert_write_allowed
    settings, store = _store(tmp_path, monkeypatch, mode="live")
    one_pass_budget(settings, store, provider="mock", today=TODAY)
    items = store.list_items(status="pending_review", kind="budget_change", limit=5)
    approved = approve(store, items[0].id)
    assert_write_allowed(settings, "apply_budget_change", approved)  # must not raise
    store.close()


def test_design_pass_is_a_no_op_when_the_subagent_is_off(tmp_path, monkeypatch):
    settings, store = _store(tmp_path, monkeypatch)
    code, stats = one_pass_design(settings, store)
    store.close()
    assert code == 0
    assert stats == {}


def test_interactive_provider_pauses_then_resumes_the_budget_note(tmp_path, monkeypatch):
    """A pause is not an error: LLMPendingInteractive must propagate all the way
    out as exit code 3, with every budget decision already made and queued -
    never a silent fall-back to canned text. Writing the answer and re-running
    must pick it up.
    """
    import json as jsonlib

    from core.config import repo_root

    settings, store = _store(tmp_path, monkeypatch, provider="interactive")
    pending_dir = repo_root() / "data" / "pending"
    prompt_path = pending_dir / "budget_note-budget-note-01.prompt.md"
    answer_path = pending_dir / "budget_note-budget-note-01.answer.json"
    for p in (prompt_path, answer_path, answer_path.with_suffix(".json.used")):
        p.unlink(missing_ok=True)
    try:
        code, stats = one_pass_budget(settings, store, provider="interactive", today=TODAY)
        assert code == 3
        assert stats["pending_review"] > 0  # every budget decision was already queued
        assert prompt_path.exists()

        answer_path.write_text(jsonlib.dumps({"note": "Test note."}), encoding="utf-8")
        code2, stats2 = one_pass_budget(settings, store, provider="interactive", today=TODAY)
        assert code2 == 0
        assert stats2["processed"] == 0  # today's decisions were already queued - idempotent
    finally:
        store.close()
        for p in (prompt_path, answer_path, answer_path.with_suffix(".json.used")):
            p.unlink(missing_ok=True)
