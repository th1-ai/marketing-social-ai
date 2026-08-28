"""tools/ads_adapters.py - the ad-platform connectors (Meta Ads, Google Ads).

`core/adapters/base.py` has no `Ads` interface: no platform exposes the same
shape the way PMS vendors roughly agree on reservations, so nothing is
registered in `core`'s adapter registry (see docs/how-it-works.md "Design
decisions" #1 - this is this repo's own "core request").

Two adapters actually work with zero credentials or a plain CSV, plus a
factory that reads `config/agent.yaml: ads.adapter`:

``mock``  fixtures/hotel/marketing_assets.json - what `make demo` and the
          tests use. Writes are recorded in-memory only.
``csv``   appends to data/exports/ad_budget_changes.csv - apply it in Meta
          Ads Manager / Google Ads by hand.
``stub``  every method raises AdapterNotImplemented with a recipe.

Both real adapters log the change instead of calling a platform API - no
ad platform's write API is called anywhere in this repo. This lives in
`tools/` rather than `core/` for the same reason `tools/reviews_adapters.py`
does in review-response-ai: `core/` is vendored byte-for-byte into every
repo in this family.
"""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.adapters.base import Adapter, AdapterNotConfigured, AdapterNotImplemented, \
    HealthCheck, guarded_write
from core.config import Settings, repo_root, sub_data_dir

BUDGET_ACTION = "apply_budget_change"


class AdsMock(Adapter):
    """In-memory mock backed by fixtures/hotel/marketing_assets.json."""

    status = "built"
    name = "ads (mock)"
    system = "ads"

    def __init__(self, settings: Settings) -> None:
        super().__init__(settings)
        self.log_path = sub_data_dir("demo") / "ads_mock.jsonl"

    def ping(self) -> HealthCheck:
        return HealthCheck(ok=True, adapter=self.name,
                           detail="reads fixtures/hotel/marketing_assets.json, writes nowhere real")

    def capabilities(self) -> set[str]:
        return {"set_budget", "pause"}

    def _record(self, action: str, asset_slug: str, **fields: Any) -> dict:
        record = {"logged_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                  "action": action, "asset_slug": asset_slug, **fields}
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        return {"ok": True, "message_id": None, "logged_to": str(self.log_path)}

    @guarded_write(BUDGET_ACTION)
    def set_budget(self, asset_slug: str, daily_budget: float) -> dict:
        return self._record("set_budget", asset_slug, daily_budget=daily_budget)

    @guarded_write(BUDGET_ACTION)
    def pause(self, asset_slug: str) -> dict:
        return self._record("pause", asset_slug)


class AdsCsv(Adapter):
    """Appends every change to data/exports/ad_budget_changes.csv.

    **Posting never calls a platform.** No ad platform's budget-write API is
    called anywhere in this repo. This is the honest v1: a change lands as a
    CSV row you (or your Claude session) apply by hand in Meta Ads Manager or
    Google Ads, then mark done. Wiring a real API is a `docs/integrations.md
    #implement-your-own` job once you have platform credentials.
    """

    status = "universal"
    name = "ads (csv)"
    system = "ads"

    def __init__(self, settings: Settings) -> None:
        super().__init__(settings)
        self.to_apply = sub_data_dir("exports") / "ad_budget_changes.csv"

    def ping(self) -> HealthCheck:
        return HealthCheck(ok=True, adapter=self.name,
                           detail=f"appends to {self.to_apply.relative_to(repo_root())}")

    def capabilities(self) -> set[str]:
        return {"set_budget", "pause"}

    def _append(self, action: str, asset_slug: str, detail: str) -> dict:
        self.to_apply.parent.mkdir(parents=True, exist_ok=True)
        is_new = not self.to_apply.exists()
        with self.to_apply.open("a", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            if is_new:
                writer.writerow(["logged_at", "action", "asset_slug", "detail"])
            writer.writerow([datetime.now(timezone.utc).isoformat(timespec="seconds"),
                            action, asset_slug, detail])
        return {"ok": True, "message_id": None, "logged_to": str(self.to_apply),
                "note": "CSV mode cannot reach a live ad account - apply this change in "
                       "Meta Ads Manager / Google Ads by hand, then check it off."}

    @guarded_write(BUDGET_ACTION)
    def set_budget(self, asset_slug: str, daily_budget: float) -> dict:
        return self._append("set_budget", asset_slug, f"daily_budget={daily_budget}")

    @guarded_write(BUDGET_ACTION)
    def pause(self, asset_slug: str) -> dict:
        return self._append("pause", asset_slug, "pause")


class AdsStub(Adapter):
    """Every write raises AdapterNotImplemented with a recipe."""

    status = "stub"
    name = "ads (stub)"
    system = "ads"

    def ping(self) -> HealthCheck:
        return HealthCheck(ok=False, adapter=self.name, detail="stub - not implemented",
                           fix_hint="Set ads.adapter to mock or csv in config/agent.yaml, or "
                                   "implement a real Meta/Google Ads client - see "
                                   "docs/integrations.md#implement-your-own.")

    def capabilities(self) -> set[str]:
        return set()

    @guarded_write(BUDGET_ACTION)
    def set_budget(self, asset_slug: str, daily_budget: float) -> dict:
        raise AdapterNotImplemented(self.name, method="set_budget")

    @guarded_write(BUDGET_ACTION)
    def pause(self, asset_slug: str) -> dict:
        raise AdapterNotImplemented(self.name, method="pause")


def get_ads(settings: Settings) -> Adapter:
    """The ad-platform connector named in `config/agent.yaml: ads.adapter`."""
    name = str(settings.agent_get("ads.adapter", "mock") or "mock").lower()
    if name == "mock":
        return AdsMock(settings)
    if name == "csv":
        return AdsCsv(settings)
    if name == "stub":
        return AdsStub(settings)
    raise AdapterNotConfigured(
        f"ads.adapter is '{name}', which does not exist.\n"
        f"  Available: mock, csv, stub.\n"
        f"  Edit config/agent.yaml, or write your own - see "
        f"docs/integrations.md#implement-your-own.")
