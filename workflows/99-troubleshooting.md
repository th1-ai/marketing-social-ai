# Workflow: troubleshooting

Read the whole error before doing anything - every tool here is written to
say what broke and what to do about it. If you fix something not covered
below, add it here.

## `make doctor` shows a FAIL

Each `FAIL` line has a `->` fix hint right under it. Common ones:

- **`hotel identity`: name is still 'Hotel Aurora'.** Expected on a fresh
  clone. Edit `config/hotel.yaml`.
- **`knowledge` warns "only example files" and points at `property.md`.**
  That hint is shared, generic core wording — this agent does not read
  `property.md`/`faq.md` for its own decisions (see `knowledge/README.md`);
  it is still worth filling in for the copilot's grounding.
- **`pms adapter` / `email adapter` show `ok` even though this agent never
  reads a PMS or sends an email.** `make doctor` checks all four core system
  families every repo in this factory shares — this agent genuinely only
  uses `email` (the exec report) and `messaging` (staff alerts); `pms` and
  `sheets` are informational rows here, not a sign anything is
  misconfigured. See `docs/integrations.md`.
- **`properties`: no properties in config/agent.yaml.** Copy
  `config/agent.example.yaml` to `config/agent.yaml` and list your own.
- **`twin pairs` warns no `budget.twin_pairs`.** Not a failure — phase 2 of
  the budget optimizer just has nothing to compare. Add pairs once you have
  an A/B test running.
- **`ads adapter` shows `stub`.** Set `ads.adapter: mock` or `csv` in
  `config/agent.yaml` — see `docs/integrations.md`.
- **`llm provider`: claude-code selected but `claude` is not on PATH.**
  Install Claude Code, or switch `llm.provider` to `interactive` or
  `anthropic` in `config/hotel.yaml`.
- **`llm provider`: ANTHROPIC_API_KEY is not set.** Add it to `.env`, or
  switch `llm.provider` to `claude-code` or `interactive`.
- **`signal sources` warns "demo fixtures" for ad_performance/content_assets/
  reviews/events.** Not a failure — the engine reads the bundled fixtures
  when nothing has been imported. Add `data/imports/<name>.json` when you
  have the data; see `docs/integrations.md`.
- **An adapter shows FAIL, not warn.** `universal`/`built` adapters fail loud
  when misconfigured (a `warn` is reserved for stubs). Read the `detail`
  column — it names the missing file or variable.

## `make demo` does not print `DEMO OK`

- Make sure `make setup` ran first (`.venv` must exist).
- `tools/demo.py` forces `llm.provider=mock`, `mode=shadow`, and a fixed
  `--as-of 2026-08-27` — it never depends on today's real date. It reads
  `fixtures/hotel/marketing_assets.json`, `fixtures/hotel/content_assets.json`
  and every `fixtures/inbound/*.json`. If you deleted or renamed one, restore
  it from git.
- Read the traceback if there is one; `tools/demo.py` does not swallow
  errors on purpose, so a fixture problem shows up immediately.

## `make run` (or `make run ARGS="--budget"` etc.) exits with code 3

Not an error. `llm.provider: interactive` parked the note prompt — every
suggestion or budget decision was already made and queued before this
happened. Read `data/pending/*.prompt.md`, write your answer to the matching
`*.answer.json` (JSON only, matching the schema shown, no prose, no code
fence), and run the same command again.

**Note on the "3":** that is `python3 tools/run.py --once`'s own exit code.
Through `make run`, the console line reads `make: *** [run] Error 3` — Make
names the real code there — but Make's own process exit status (what a
script sees as `$?`) is always **2** for any failed recipe, whatever number
the recipe actually returned; that is GNU Make's own convention, not
something this agent controls. If you are scripting against the exit code
(to detect "3 = pending" vs "1 = real error"), call
`python3 tools/run.py --once` directly instead of going through `make run`.

## A suggestion or budget change never appears in the queue

- Check it is not simply already there: everything is keyed per calendar day
  (`docs/how-it-works.md` "Idempotency") — re-running the same day changes
  nothing for a slug that already has an open or resolved-today decision.
- A `hold` budget row or a muted `event_signal` suggestion is written
  straight to `skipped` — check `python3 tools/review.py list --status
  skipped`, it is there, not lost.
- Confirm the ad is actually configured `status: active` with a
  `daily_budget` in `fixtures/hotel/marketing_assets.json` (or your own
  `data/imports/marketing_assets.json`) — a paused or draft ad is skipped by
  every engine.

## An item is stuck at `sending`

A process died between claiming an item and finishing the action.
`tools/run.py` calls `core.store.Store.reap_stuck_sending()` on every
suggestions/budget pass, which moves anything stuck for more than 30 minutes
to `failed` so you see it in the queue instead of it vanishing. Use
`python3 tools/review.py retry <id>` once the cause is fixed.

## A budget change gets approved but nothing applies

In `mode: shadow`, this is expected — see `workflows/80-review.md` step 4.
`python3 tools/review.py send` prints `blocked <id> (approval kept): ...`
and the item goes straight back to `approved`, not `failed`; run `list` and
it is there waiting for `mode: live`.

In `mode: live`, check `python3 tools/review.py show <id>` — a real write
error lands the item in `failed` with the reason on its `error` field.
With `ads.adapter: mock`, every "applied" change is only ever logged to
`data/demo/ads_mock.jsonl`; with `csv`, check
`data/exports/ad_budget_changes.csv`.

## The suggestion queue is empty except events

That is the honest answer, not a bug, on a small or quiet fixture set —
`headline_test` needs a creative at least `suggestions.headline_min_age_days`
old, `review_ad` needs a theme mentioned `suggestions.review_min_mentions`
times, `landing_page` needs a real CTR/conversion gap. Check
`docs/how-it-works.md` for every category's trigger.

## `python3 tools/*.py` says `ModuleNotFoundError: No module named 'core'`

You ran it with a Python that is not the repo's virtualenv, or from outside
the repo root. Use `make run` / `make doctor` / etc. (they call
`.venv/bin/python` for you), or run `.venv/bin/python tools/run.py` directly
from the repo root.

## Still stuck

`data/logs/*.jsonl` has every decision the agent made, in order, with a run
id. `python3 tools/review.py show <id>` has the full event trail for one
item. If neither explains it, that is a real bug — describe exactly what you
ran and what you expected, and ask.
