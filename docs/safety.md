# Guardrails and safety

This agent drafts creative that guests will eventually see, and it can move
real ad spend. Everything below is built in, not optional, and this page
explains what it does and what is left for you to decide.

## The two modes

| Mode | What happens |
|---|---|
| `shadow` (default) | The agent reads, thinks, drafts and queues. It **never** moves a budget, **never** notifies staff, and **never** sends the exec report email. Approving, editing or rejecting a draft records your decision but sends nothing. At go-live, `python3 tools/review.py stale` clears that shadow-era queue so nothing old goes out by surprise. |
| `live` | Items you approved are really acted on. Everything else still waits — there is no auto-apply tier in this agent, see below. |

`mode` lives in `config/hotel.yaml`. It is a global kill switch: flipping it
back to `shadow` stops every action immediately, mid-schedule, with no other
change. `config/agent.yaml` can be stricter than `hotel.yaml`, never looser.

Two more brakes:

- `make run ARGS="--dry-run"` (any pass: `--budget`, `--content`, `--design`,
  `--performance`) computes everything and writes nothing, even in live mode.
- `review.require_approval_for` in `config/hotel.yaml` lists the actions that
  need a human even in live mode: `send_email`, `send_message`, `pms_write`,
  `payment`, `publish`, `apply_budget_change`. Nothing in this agent's own
  config can remove `apply_budget_change` from that list — a budget change
  always needs a person, forever.

Every outbound action in the codebase goes through one function,
`core/review.py:assert_write_allowed`. There is no second path.

## Nothing here auto-applies

Unlike some agents in this family, Marketing & Social AI has no "guarded
autopilot" tier that lets a low-risk item through without a person. Every
suggestion, every budget change, every design request, every ROAS alert and
every exec report lands at `pending_review` (or `skipped`, when it is
informational — a muted event suggestion, a `hold` budget row) and stays
there until a human decides. This is not a config knob; it is how the code
is written (`docs/how-it-works.md` "Design decisions" #12) — the roster's
`cant` makes the promise unconditional for budget moves ("Won't post or move
a budget without approval") and this repo holds every other kind to the
same bar.

## The review queue

```bash
make review                                  # what is waiting
python3 tools/review.py show <id>             # the full draft and how it got there
python3 tools/review.py approve <id>
python3 tools/review.py edit <id> --field-file changes.json
python3 tools/review.py reject <id> --reason "not this quarter"
python3 tools/review.py send                  # act on everything approved/edited
```

An item moves `new -> dispatched -> pending_review` and then waits. Only
`tools/review.py` can write `approved`, `edited` or `rejected`; only `send`
can write `sending`/`sent`. A crash between "about to act" and "done" is
picked up on the next pass (`store.reap_stuck_sending()`) and shown to you
as `failed` rather than silently retried.

## What the agent will not do

- Move a budget, notify staff, or email the exec report while `mode: shadow`.
- Act on an item a human has not approved.
- Take a payment or move money — no payment adapter exists in this agent at
  all.
- Push a creative to the library, then launch it as a live ad. Pushing is a
  local organizing step; launching is a human task this repo does not
  model, same as the source it was built from.
- Invent an ad-performance number, a review quote, or an asset that is not
  in `fixtures/`/`data/imports/`. The copilot's system prompt is explicit:
  "only state numbers that come from your tools."
- Compose from anything outside the approved photo library and brand kit.
  There is no image generation at runtime.

## Data handling

**What leaves your machine.** With `llm.provider: anthropic` or
`claude-code`, the copilot question or the narration prompt goes to
Anthropic — never guest personal data, since this agent has no guest inbox;
the prompt carries ad performance numbers, brief text, and property facts.
With `llm.provider: mock` or `interactive`, nothing leaves the machine at
all.

**What is stored, and where.** Everything lives in `data/` inside this
folder: `agent.db` (SQLite), `logs/*.jsonl`, `exports/`. `data/` is
gitignored. There is no cloud service behind this repo and no telemetry.

**Card numbers are redacted on the way in.** Any free text this agent
ingests (a design request brief, a copilot question) passes through
`core/redact.py` before it is stored, logged or put into a prompt. Nothing
in config turns this off.

**Retention.** `privacy.retention_days` (default 365) is how long processed
items stay in the database. Deleting `data/agent.db` deletes everything the
agent knows.

## GDPR, in practice

If you are in the EU or handle EU guests' data, the short version:

- **You are the controller.** This software runs on your machine, under
  your control, on your data. TH1 does not receive it.
- **Your model provider is a processor.** If you use the `anthropic` or
  `claude-code` provider, Anthropic processes what you send it (ad
  performance numbers, briefs, review excerpts) on your behalf. Check their
  data processing terms and record them in your processing register.
- **Purpose and minimisation.** Do not put staff phone numbers or full
  guest histories in `knowledge/`; this agent has no reason to read either.
- **Retention.** Set `privacy.retention_days` to what your own policy says,
  not to the default.

This is a practical summary, not legal advice.

## Telling guests they are seeing AI-assisted content

The EU AI Act (Article 50) requires labelling AI-generated content in some
circumstances, and it is good practice everywhere. Every creative this
agent generates — a headline, a social caption, a piece of ad copy — is a
draft: a human reviews it, a human pushes it to the library, and a human
decides how (and whether) to disclose AI assistance on the finished post,
following your own platform's and jurisdiction's rules. This repo does not
publish anything itself, so there is no automated disclosure line to get
wrong — but do not strip that judgement out of the human step. If your
workflow does end up auto-posting downstream of this repo, add a line like:

> This ad/post was drafted with AI assistance and reviewed by our team.

No em dashes in any copy a guest might see — see `README.md` "Customising."

## Subscription or API: an honest note

Two ways to pay for the reasoning:

**Your Claude Code subscription** (`llm.provider: claude-code` or
`interactive`). Flat monthly cost, no per-message billing. This is
genuinely the cheapest way to run a small hotel's marketing desk — this
agent calls a model for two narration notes and one copilot question at a
time, nowhere near the volume a guest-facing agent sees.

The caveat, plainly: a personal Pro or Max subscription is intended for
interactive use, and Anthropic's usage policy and rate limits apply to
automated use of it. A handful of scheduled runs a day is a normal way to
work. Read the terms and decide for yourself.

**The Anthropic API** (`llm.provider: anthropic`). Pay per token, no
ambiguity about automated use, proper rate limits, and usage you can
attribute. `make report` shows what you are spending.

Start on the subscription while you are learning what the agent does. Move
to the API when it becomes part of how the hotel runs.

## If something goes wrong

1. `mode: shadow` in `config/hotel.yaml`, or `AGENT_MODE=shadow` in `.env`.
   Every action stops on the next pass.
2. Remove the schedule (`crontab -e`, `launchctl unload`, or
   `systemctl disable --now <slug>.timer`).
3. `make doctor` to see what the agent thinks its state is.
4. `data/logs/*.jsonl` has every decision, with the run id, in order.
