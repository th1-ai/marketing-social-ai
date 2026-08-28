"""Sample-data marking: fixture data must never be approved as the hotel's own.

On a fresh clone every `config/*.example.yaml` ships its adapters on `mock`, so
a real (not `make demo`) pass reads the bundled fixtures. Core tags any item
whose source came through a mock adapter with payload `_sample: True`
(`core.store.Store.upsert_item` via `core.adapters.is_sample_source`;
`item.is_sample` reads it back) - this repo does not re-implement the tagging,
it only has to SHOW it, in `make review`'s `list` and `show` output.

`config/agent.yaml: systems_used: [email, messaging]` is the other half: this
agent never calls the PMS (its signals are `data/imports/*.json`, see
docs/integrations.md), so `systems.pms.adapter` stays `mock` forever and must
never be treated as sample-data-producing.

`tests/conftest.py`'s autouse fixture isolates AGENT_CONFIG_DIR/AGENT_REPO_ROOT
for every test in this module.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.config import load_settings
from core.store import Store
from tools.review import cmd_list, cmd_show

PAYLOAD = {"to": "manager@example.com",
           "subject": "Marketing performance — Hotel Aurora, 2026-09-01",
           "body": "ROAS 6.2 across four live ads."}


def _sample_item(tmp_path):
    """One queued exec_report on a fresh clone: `systems.email.adapter` is
    still the shipped `mock` default, so core tags the item as sample data."""
    settings = load_settings()
    assert settings.demo is False            # the real path, not `make demo`
    assert settings.systems.email.adapter == "mock"   # the shipped default
    store = Store(settings, path=tmp_path / "test.db")
    item = store.upsert_item("email", "2026-09-01", kind="exec_report", payload=PAYLOAD)
    store.set_fields(item.id, draft=PAYLOAD)
    store.transition(item.id, "pending_review", "agent")
    return store, item


def test_a_real_pass_on_the_mock_default_tags_its_item_sample(tmp_path):
    store, item = _sample_item(tmp_path)
    # While a system this agent USES (email) is still on the mock adapter,
    # every item the run produces is sample-derived - whatever its source.
    pms_item = store.upsert_item("pms", "res-1", kind="suggestion", payload={"title": "x"})
    store.close()
    assert item.is_sample is True
    assert item.payload.get("_sample") is True
    assert pms_item.is_sample is True


def test_unused_mock_pms_does_not_tag_once_used_systems_are_connected(tmp_path, monkeypatch):
    """`systems_used: [email, messaging]` excludes the PMS: with email and
    messaging on real adapters, a mock PMS must not mark items as sample."""
    cfg = tmp_path / "cfg"; cfg.mkdir()
    (cfg / "hotel.yaml").write_text(
        "systems:\n  email:\n    adapter: imap\n  messaging:\n    adapter: webhook\n",
        encoding="utf-8")
    (cfg / "agent.yaml").write_text("systems_used: [email, messaging]\n", encoding="utf-8")
    monkeypatch.setenv("AGENT_CONFIG_DIR", str(cfg))
    settings = load_settings()
    assert settings.systems.pms.adapter == "mock"
    store = Store(settings, path=tmp_path / "t2.db")
    pms_item = store.upsert_item("pms", "res-2", kind="suggestion", payload={"title": "y"})
    store.close()
    assert pms_item.is_sample is False


def test_review_list_flags_the_sample_item(tmp_path, capsys):
    store, item = _sample_item(tmp_path)
    capsys.readouterr()
    cmd_list(store, SimpleNamespace(status=None, kind=None, limit=50))
    store.close()
    out = capsys.readouterr().out
    assert "[SAMPLE DATA]" in out
    assert "shipped sample fixtures, not your property" in out


def test_review_show_warns_before_the_json(tmp_path, capsys):
    store, item = _sample_item(tmp_path)
    capsys.readouterr()
    cmd_show(store, SimpleNamespace(id=item.id))
    store.close()
    out = capsys.readouterr().out
    assert out.startswith("[SAMPLE DATA]")
