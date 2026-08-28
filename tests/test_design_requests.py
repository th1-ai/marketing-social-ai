"""Tests for tools/design_requests.py - filing and listing a design request.

Regression for SIMULATION.md Finding 2: `tools/design_requests.py list` with
no `--status` used to default to `core.review.ACTIONABLE_STATES`, which does
not include `new` - so a request filed a second ago (before `--design` has
drafted it) reported "No design requests waiting," even though
`workflows/22-brand-collateral.md`'s own worked example runs `new`
immediately followed by `list` with no flag. Fixed by defaulting `list` to
`ACTIONABLE_STATES | {"new"}` for this kind only (core/review.py is
untouched).
"""

from __future__ import annotations

import sys
from argparse import Namespace
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.store import Store
from tools.design_requests import cmd_list, cmd_new


def _store(tmp_path):
    return Store(path=tmp_path / "test.db")


def _new_args(**overrides):
    base = dict(brief="Terrace poster for the derby", kind="poster", property="hotel-aurora",
               season="summer", subject="dining", audience="couples", requested_by="",
               due=None)
    base.update(overrides)
    return Namespace(**base)


def test_new_then_list_with_no_status_shows_the_fresh_request(tmp_path, capsys):
    """Reproduces workflows/22-brand-collateral.md's worked example verbatim:
    `new` then `list` with no flag - must not read "No design requests
    waiting" for a request that was just filed successfully.
    """
    store = _store(tmp_path)
    try:
        code = cmd_new(store, _new_args())
        assert code == 0
        filed_line = capsys.readouterr().out
        assert "filed" in filed_line

        code = cmd_list(store, Namespace(status=None, limit=50))
        assert code == 0
        out = capsys.readouterr().out
        assert "No design requests waiting." not in out
        assert "poster" in out
    finally:
        store.close()


def test_list_with_explicit_status_still_filters(tmp_path, capsys):
    store = _store(tmp_path)
    try:
        cmd_new(store, _new_args())
        capsys.readouterr()
        code = cmd_list(store, Namespace(status="pending_review", limit=50))
        assert code == 0
        out = capsys.readouterr().out
        # a brand-new request has not been drafted yet - not pending_review.
        assert "No design requests waiting." in out
    finally:
        store.close()


def test_list_new_explicitly_also_works(tmp_path, capsys):
    store = _store(tmp_path)
    try:
        cmd_new(store, _new_args())
        capsys.readouterr()
        code = cmd_list(store, Namespace(status="new", limit=50))
        assert code == 0
        out = capsys.readouterr().out
        assert "No design requests waiting." not in out
    finally:
        store.close()
