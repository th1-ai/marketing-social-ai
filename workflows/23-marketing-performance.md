# Workflow: Marketing Performance AI ("The Attributor")

Objective: watch spend efficiency, alert on a real ROAS drop within a day,
and put a Monday-morning read in front of the marketing lead — without
moving a single euro itself. Off by default; see `docs/sub-agents.md`.

## Turning it on

```yaml
# config/agent.yaml
subagents:
  marketing_performance:
    enabled: true
    roas_drop_alert_pct: 0.25   # week-over-week drop that raises an alert
    exec_report_day: monday
    exec_report_hour: 9
```

## Running it

```bash
make run ARGS="--performance"
make run ARGS="--performance --as-of 2026-09-01"
```

Two things happen every pass:

1. **ROAS-drop alerts.** Each creative's trailing 7-day ROAS is compared to
   the 7 days before it; a drop past `roas_drop_alert_pct` raises a
   `roas_alert` item. A plain, explainable threshold — not a statistical
   model (`docs/how-it-works.md` "Design decisions" #7).
2. **The exec report.** A markdown digest — the 90-day KPI strip, this
   week's ROAS drops, and what is waiting in the queue — is always exported
   to `data/exports/exec_report_<date>.md`. It never depends on the LLM or
   the mailbox being configured.

## Reviewing and sending an alert

```bash
make review
python3 tools/review.py show <id>
python3 tools/review.py approve <id>
python3 tools/review.py send
```

Approving a `roas_alert` and sending it calls
`core.adapters.get_messaging().notify_staff()` — with `messaging.adapter:
mock` that goes nowhere real, with `webhook` it posts to whatever URL you
configured (Zapier / Make / n8n).

## Reading the exec report

```bash
cat data/exports/exec_report_$(date +%Y-%m-%d).md
```

This agent has no write path of its own beyond the alert notify — "its
numbers feed the budget desk, where changes apply only inside safety caps
and with your approval" (roster `cant`). Do not wire this agent's output
directly into a budget change; that is what `workflows/15-budget.md` is for.

## Edge cases

- **No alert two weeks running.** `find_roas_drops` needs a full 7 days of
  prior-week spend to compute a baseline — a brand-new ad with no prior week
  never triggers a false alert on day one.
- **The exec report shows a blank ROAS-drops section.** That is the honest
  answer, not a bug — every creative held or improved its return.
