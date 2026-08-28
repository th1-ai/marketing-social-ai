# Workflow: working the review queue

Objective: turn a queued item into a decision — approve, edit, or reject —
and, once approved, actually act on it. One queue holds all four kinds this
agent produces: suggestions, budget changes, design requests, and ROAS
alerts.

Nothing leaves this repo without going through this. `mode: shadow` blocks
every guarded write — `apply_budget_change`, `send_message` — for **every**
item, approved or not; see `docs/safety.md` for the full guard.

## Steps

1. **See what is waiting.**
   ```bash
   make review
   python3 tools/review.py list --kind budget_change
   python3 tools/review.py list --status pending_review
   ```
   Each line shows the item id, its status, its kind, and a short label.

2. **Read one in full.**
   ```bash
   python3 tools/review.py show <id>
   ```
   Prints the draft and the full event history for that item. Summarise it
   for the marketing lead in plain language — what changed, why, and what
   it is worth — do not paste raw JSON at them.

3. **Decide.**
   ```bash
   python3 tools/review.py approve <id>
   python3 tools/review.py edit <id> --field-file changes.json   # {"to_daily": 45}
   python3 tools/review.py reject <id> --reason "not this quarter"
   ```
   `--field-file` takes a small JSON file of `{field: new_value}` pairs
   merged into the draft — useful for nudging a budget change's `to_daily`
   before approving it.

4. **Act on what was approved.**
   ```bash
   python3 tools/review.py send
   ```
   Dispatches every `approved`/`edited` item by kind (`docs/how-it-works.md`):
   a `budget_change` calls the ads adapter, a `roas_alert` notifies staff, a
   `suggestion` or `design_request` has nothing external to send — approval
   already was the decision, so it just closes out. In `mode: shadow` this
   always reports "blocked... nothing leaves in shadow mode," for every
   kind, whatever was approved — that is the point.

5. **A failed action.** `send` marks the item `failed` with the error
   attached.
   ```bash
   python3 tools/review.py retry <id>
   ```
   re-queues it for another attempt after you have fixed the cause (usually
   the ads adapter or the messaging adapter — `make doctor` will say which).

## Rules

- Only `tools/review.py` writes `approved` / `edited` / `rejected`.
- A `budget_change` at `action: hold` never appears here — it is written
  straight to `skipped`, informational only.
- A muted `event_signal` suggestion never appears here either.
- Confirm with the marketing lead before sending anything, even an approved
  item, the first few times. `workflows/90-go-live.md` covers when to stop
  doing that.
