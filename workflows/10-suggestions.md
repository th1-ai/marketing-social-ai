# Workflow: the suggestion queue

Objective: refresh the standing queue of evidence-backed marketing ideas —
event radar, headline tests, review-quote ads, cross-property plays,
landing-page callouts — so a human can approve, dismiss, or ask the copilot
about any of them. This is the Bard's own daily job, separate from the
budget optimizer (`workflows/15-budget.md`).

## Steps

1. **Check the agent is healthy.**
   ```bash
   make doctor
   ```
   A `warn` on "signal sources" means one or more of `ad_performance`,
   `content_assets`, `reviews`, `events` is reading the demo fixtures instead
   of your own `data/imports/` file — fine for a first look, not for a real
   run.

2. **Run one pass.**
   ```bash
   make run                              # generate/refresh the queue
   make run ARGS="--dry-run"             # compute everything, write nothing
   make run ARGS="--as-of 2026-09-01"    # rehearse against a specific date
   ```
   This never calls a model — the queue itself is deterministic, see
   `docs/how-it-works.md`.

3. **Read what it found.** Every run prints how many suggestions it
   considered and how many were queued versus skipped/muted. A muted
   `event_signal` (rule `event_radar` off) never reaches the queue at all —
   that is by design, not a bug.

4. **Show what is waiting.**
   ```bash
   make review
   python3 tools/review.py show <id>
   ```
   Each suggestion carries its category, a rationale in plain language, a
   projected impact, and the evidence it was built from. Read the rationale
   back to the user — do not paste raw JSON.

5. **Act on their decision.**
   ```bash
   python3 tools/review.py approve <id>
   python3 tools/review.py reject <id> --reason "not this quarter"
   python3 tools/review.py send             # closes out an approved suggestion
   ```
   Approving a suggestion never spends money or posts anything — it is the
   decision itself, not a trigger for an external write. An approved
   `event_signal` or `new_creative` suggestion is what Content Creation AI
   (`workflows/21-content-creation.md`, off by default) picks up to generate
   a campaign from, if you turn it on.

6. **Ask the copilot, when a number needs unpacking.**
   ```bash
   python3 tools/copilot.py ask "Which creative should I put more money behind?"
   ```
   Grounded in the same 30-day ad performance the budget desk reads — it
   will not invent a figure. It can file at most one new suggestion per
   question, only when the numbers clearly warrant it.

7. **Report.**
   ```bash
   make report
   ```

## Edge cases

- **A suggestion you already saw today does not come back.** Suggestions are
  keyed by a stable slug (`docs/how-it-works.md` "Idempotency") — re-running
  the same day refreshes nothing for a suggestion that already exists.
- **A held item you never look at.** `store.mark_stale()` runs every pass and
  ages anything sitting in `pending_review` for more than 72 hours to
  `stale`. Revive it with `python3 tools/review.py show <id>`.
- **Nothing is ever auto-approved.** Unlike some agents in this family,
  Marketing & Social AI has no "guarded autopilot" tier — every suggestion,
  every budget change, every design request and every ROAS alert waits for a
  person. See `docs/how-it-works.md` "Design decisions" #12.
