---
name: marketing-social-ai
description: Run Marketing & Social AI ("The Bard") — The marketing desk for the whole property.. Use when the user asks to run the agent, check what is waiting for review, approve or reject a draft, or asks how the agent is doing. Trigger phrases: "run The Bard", "/marketing-social-ai", "check the queue", "what is waiting for me", "approve that draft".
---

# Marketing & Social AI

Runs Marketing & Social AI and works its review queue. Everything happens
from the repo root; every command below exists and works.

## Before anything else

Read `README.md` if you have not this session, and
`workflows/10-suggestions.md` / `workflows/15-budget.md` for the main
loops. If the user has never run this agent, start at
`workflows/00-setup.md` instead and walk them through it.

## The loop

**1. Check the agent is healthy.**

```bash
make doctor
```

Any `FAIL` line has a fix hint. Fix it before going further. `WARN` lines
are worth mentioning but do not stop the run.

**2. Run one pass.**

```bash
make run                        # the suggestion queue
make run ARGS="--budget"        # the budget optimizer
make run ARGS="--dry-run"       # compute everything, write nothing
```

Sub-agent passes (`--content`, `--design`, `--performance`) only do
anything once their `config/agent.yaml: subagents.*.enabled` flag is set —
see `workflows/21-content-creation.md`, `22-brand-collateral.md`,
`23-marketing-performance.md`.

If `llm.provider` is `interactive`, the run will stop with exit code 3 and
park a prompt in `data/pending/`. That is expected — every decision was
already made and queued before this happened. Read the `*.prompt.md`,
write your answer as JSON to the matching `*.answer.json` following the
schema exactly, then run the same command again.

**3. Show what is waiting.**

```bash
make review
python3 tools/review.py show <id>
```

Summarise it for the user in plain language: what kind of item it is
(suggestion, budget change, design request, ROAS alert), what it found,
and what it is worth. Do not paste raw JSON at them.

**4. Act on their decision.**

```bash
python3 tools/review.py approve <id>
python3 tools/review.py edit <id> --field-file <path.json>
python3 tools/review.py reject <id> --reason "<why>"
python3 tools/review.py send
```

Read the draft back to them before approving. `send` dispatches by kind —
a budget change calls the ads adapter, a ROAS alert notifies staff, an exec
report emails the manager contact, a suggestion or design request just
closes out.

**5. Report.**

```bash
make report
```

## Rules

- **Never act in shadow mode**, and never work around a blocked write. The
  error message says what to do.
- **Going live is the hotel's decision.** Only raise it after
  `workflows/90-go-live.md` has been worked through.
- **Confirm before anything irreversible** — moving a budget, notifying
  staff, sending the exec report — even when it is approved.
- **Never print or paste a credential.**
- If a run fails, read the whole error, fix the cause, re-run, and note
  what you learned in `workflows/99-troubleshooting.md`.
