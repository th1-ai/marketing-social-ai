# Workflow: the budget optimizer

Objective: pause the bleeders, settle your declared A/B twin pairs, and feed
the winners inside the safety cap — then wait. This is the piece of the
roster's promise that touches real money, so nothing here ever applies
itself; see `docs/how-it-works.md` "Design decisions" #12.

## Steps

1. **Check the agent is healthy.**
   ```bash
   make doctor
   ```
   A `warn` on "twin pairs" means `config/agent.yaml: budget.twin_pairs` is
   empty — phase 2 (settle the A/B twins) has nothing to compare. That is
   fine if you have not set up an A/B test; it just means that phase never
   fires.

2. **Run one pass.**
   ```bash
   make run ARGS="--budget"
   make run ARGS="--budget --dry-run"
   make run ARGS="--budget --as-of 2026-09-01"
   ```
   If `llm.provider` is `interactive`, the pass finishes the real work first
   (every pause/reallocate/scale-up decision is already made and queued) and
   then stops with exit code 3 while it waits for you to write the note.
   Read `data/pending/*.prompt.md`, answer into the matching
   `*.answer.json`, and re-run the same command. (That "3" is
   `tools/run.py`'s own exit code. Through `make run`, the console prints
   `make: *** [run] Error 3` — Make's own exit status is always 2 for any
   failed recipe, not 3, whatever the command underneath actually returned;
   see `workflows/99-troubleshooting.md`.)

3. **Read what it did.** Every pass prints its six-step thinking log: the
   30-day funnels pulled, the return spread, what got paused and how much
   that frees, what got rebalanced between twins, what got scaled or held,
   and the headline number. Summarise this in plain language — how many
   moves, the euro impact, what got held and why.

4. **Show what is waiting.**
   ```bash
   make review
   python3 tools/review.py show <id>
   ```
   `show` prints the reason and the exact from/to daily budget. Do not paste
   raw JSON at the user — read the reason and the numbers back to them.

5. **Act on their decision.**
   ```bash
   python3 tools/review.py approve <id>
   python3 tools/review.py reject <id> --reason "not touching that campaign yet"
   python3 tools/review.py send
   ```
   In `mode: shadow` this always reports "blocked... nothing leaves in
   shadow mode" — that is the point. Nothing applies until
   `workflows/90-go-live.md` has been worked through. Once live, `send`
   calls `tools/ads_adapters.py`'s `set_budget`/`pause` for each approved
   change — with `ads.adapter: mock` that writes nowhere real, with `csv` it
   appends a row to `data/exports/ad_budget_changes.csv` for you to apply by
   hand in Meta Ads Manager / Google Ads.

6. **Report.**
   ```bash
   make report
   ```

## Edge cases

- **A `hold` row never appears in the review queue.** Brand-term ads (ROAS
  above `hold_roas_above`) are written straight to `skipped` — informational
  only, they never wait for a decision because there is no decision to make.
- **A change you already queued today does not come back.** Changes are
  keyed `(run_date, asset_slug, action)` — re-running the same day refreshes
  nothing already open. Tomorrow's run gets a fresh key.
- **The twin shift looks small.** `twin_shift_pct` (default 40%) is off the
  *loser's* current daily budget, rounded to the nearest €5, floor €5 — see
  `docs/how-it-works.md` "The budget steps."
