# Workflow: shadow to live

Objective: decide, together with the marketing lead, whether Marketing &
Social AI is ready to actually move a budget or notify staff instead of
only drafting — and make the change safely if so.

This is the hotel's decision, never the agent's. Do not suggest it until the
checklist below is genuinely true, and when you do raise it, say plainly
what changes: **approved budget changes start actually reaching your ad
platform (or the CSV export you apply by hand), and approved ROAS alerts
start actually notifying staff.**

There is no "guarded autopilot" tier to switch on here, unlike some agents
in this family — going live never makes anything auto-apply on its own.
Every kind still needs a person's `approve` first, forever
(`docs/how-it-works.md` "Design decisions" #12).

## Checklist

- [ ] `make doctor` is clean (no `FAIL` lines). `warn` on `mode` and `llm
      provider` is expected until you flip them.
- [ ] `config/hotel.yaml` has the real property details, and
      `config/agent.yaml` has your real properties, rules and budget
      thresholds — not Hotel Aurora's.
- [ ] `fixtures/hotel/content_assets.json` has been replaced (or overridden
      via `data/imports/content_assets.json`) with your own brand kit — a
      generated creative going live on the sample photos would be composing
      from nothing real.
- [ ] `ads.adapter` in `config/agent.yaml` is a real one (`csv`, not `mock`)
      and `make doctor` shows it healthy. Going live on `mock` would only
      ever touch the fixtures.
- [ ] At least a few days of real `make run` passes have gone through the
      review queue — not just the demo. Read `make report`: how many
      suggestions, how many budget changes, how many you rejected.
- [ ] You have looked at a week of budget-change reasons and they make
      sense — the thresholds (`config/agent.yaml: budget`) match how this
      property actually wants ad spend managed, not the shipped defaults
      blindly.
- [ ] If any sub-agent is on, its inputs are real, not the bundled fixtures.

## Making the change

1. Edit `config/hotel.yaml`:
   ```yaml
   mode: live
   ```
2. `review.require_approval_for` still lists `apply_budget_change` and
   `send_message` by default — it should, forever. Going live only means an
   **approved** item actually acts; it does not change what needs approval.
   There is no config in this agent that skips a human's yes.
3. **Clear the shadow backlog.** Everything sitting in `pending_review` from
   before today was computed against yesterday's numbers and is stale by the
   time you trust the drafts:
   ```bash
   python3 tools/review.py stale
   ```
   Re-run `make run ARGS="--budget"` to get fresh proposals against the
   current 30-day window.
4. Run `make doctor` again to confirm.
5. Watch one action go through by hand before trusting the schedule:
   ```bash
   make run ARGS="--budget --as-of $(date +%F)"
   python3 tools/review.py list
   python3 tools/review.py approve <id>
   python3 tools/review.py send
   ```
6. Tell the marketing lead exactly what just changed, in plain language:
   from now on, an item they approve actually reaches the ads adapter or
   staff notify; nothing changes about what waits for their yes.

## Going back to shadow

```yaml
mode: shadow
```
in `config/hotel.yaml`, or `AGENT_MODE=shadow` in `.env` for one run. Either
stops every action on the next pass, mid-schedule, with no other change
required.
