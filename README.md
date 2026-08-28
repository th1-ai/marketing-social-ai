# Marketing & Social AI — "The Bard"

The marketing desk for the whole property.

## What it does

The marketing desk for the whole property. It keeps a live queue of suggestions with the evidence and projected € attached — event radar (a stadium concert becomes an ad idea before demand peaks), headline tests, review-quote ads, budget shifts, cross-property plays. It composes on-brand campaigns from your own photo library and brand kit — creatives and video — and manages daily ad budgets inside safety caps: pausing losers, scaling winners, reallocating between look-alike ads, with nothing applied until you approve. A marketing copilot answers questions over the live ad data and files its own suggestions into the queue. And it still does the bread and butter: posts, newsletters, and seasonal offers timed to occupancy gaps.

## What it won't do

Won't post or move a budget without approval. The brand guard checks every creative against your palette, type and voice rules, and budget moves stay inside daily safety caps — only clearly unprofitable ads can even be paused.

## Why it matters

Keeps marketing consistent and demand-aware without a full-time marketer.

## What to expect

3–5× content cadence plus ad budgets tuned continuously — waste paused in days, winners scaled inside caps.

The roster text above is quoted exactly as it appears on the demo
platform's agent menu — this repo does not promise more than that, and
does not promise less. ROI figure: `+300%` Content output (revenue).

## Who it's for

Independent hotels and small groups running their own paid ads and their
own content — the marketing lead who has a Meta/Google Ads account, a
photo library, and a growing list of things they meant to test but never
got to. It replaces the "check the dashboards, notice something is
bleeding, mean to fix it" part of that job, not the person who sets
positioning and pricing strategy.

You will get the most from this repo if:

- You have active Meta and/or Google ad campaigns and can export their
  daily performance, even by hand.
- You have a photo library you already own the rights to — this agent
  composes only from what you give it, never generates an image at
  runtime.
- You are comfortable reviewing every suggested change before it
  ships, at least at first — this ships in shadow mode and there is no
  auto-apply tier to skip that step later.
- You want the discipline of testing one thing at a time (a CTA colour, a
  headline) rather than changing everything at once and guessing what
  worked.

It is less of a fit if you have no ad spend to manage at all (the budget
optimizer and the suggestion queue's `budget_shift`/`headline_test`
categories need something running), or if you would rather have an agency
handle taste and positioning entirely — this agent drafts at volume, it
does not replace a creative director.

## How it works

One standing suggestion queue and one deterministic budget optimizer, plus
three folded-in sub-agents that read the same brand kit and performance
numbers — no randomness, no model call anywhere near a euro of spend.

```mermaid
flowchart TD
    A[ingest: ad performance, content assets, reviews, events] --> B{which pass}
    B -- default --> C[suggestion_engine: generate the queue]
    B -- --budget --> D[budget_engine: analyse_budget]
    B -- --content, Editor on --> E[content_engine: generate_campaign]
    B -- --design, Art Director on --> F[design_engine: draft design requests]
    B -- --performance, Attributor on --> G[attribution_engine: ROAS alerts + exec report]
    C --> H[items: pending_review / skipped]
    D --> H
    F --> H
    G --> H
    H --> I[review queue - workflows/80-review.md]
    I -- approve --> J[tools/review.py send: apply, notify, email, or just close out]
    E --> K[campaigns/creative_drafts table - a gallery, not a queue]
```

`tools/budget_engine.py` and `tools/suggestion_engine.py` are pure
functions with no I/O: plain dicts in, a list of changes/suggestions and a
step-by-step thinking log out. `tools/run.py` is the only place that talks
to the store, the ads adapter, or the LLM. The **only** model calls in this
agent are two narration notes about a run that already finished, and one
grounded copilot question — none of them can move a euro or push a
creative. Full detail, the exact budget-optimizer thresholds, and the
twelve design decisions taken where the source this repo was built from
left a gap: `docs/how-it-works.md`.

### The two modes

| Mode | What happens |
|---|---|
| `shadow` (default) | Reads, thinks, drafts every suggestion and budget change, and queues. **Never** applies a budget, notifies staff, or emails the exec report — including an item you already approved; the approval is recorded, acting waits for `mode: live`. |
| `live` | Items you approved actually act. Everything else still waits — there is no autopilot tier that skips your approval, in either mode. |

### The review loop

Nothing acts without a person saying so. `workflows/80-review.md` covers
the full loop: list, show, approve, edit, reject, send — for all five kinds
this agent produces.

### What runs when

| Workflow | Cadence | Provider used |
|---|---|---|
| `workflows/10-suggestions.md` (`tools/run.py`) | daily | none — the queue itself is deterministic |
| `workflows/15-budget.md` (`tools/run.py --budget`) | daily | narration only |
| `workflows/21-content-creation.md`, off by default | weekly | narration only |
| `workflows/22-brand-collateral.md`, off by default | every 30 min | none |
| `workflows/23-marketing-performance.md`, off by default | Monday 09:00 | none |
| `workflows/80-review.md` (`tools/review.py`) | whenever a human is available | none — queue operations only |

```bash
python3 tools/schedule.py --all
```

prints one ready-to-paste cron/launchd/systemd snippet per job, read
straight from `config/agent.yaml: schedule:` — see "Run it" below.

## What you need

| Item | Required? | Notes |
|---|---|---|
| A computer or small server that can run Python 3.11+ | Yes | Your laptop is fine to start; `workflows/90-go-live.md` covers scheduling it properly. |
| A Claude Code subscription, or your own Anthropic API key | Yes | The `interactive` provider uses the Claude Code session you already have open — zero extra cost, and the model only ever writes a note or answers a grounded question. |
| A daily-performance export from Meta Ads and/or Google Ads, even by hand | Yes | Starts on `mock` fixtures; `data/imports/ad_performance.json` works with any export you can turn into that shape. |
| Your own rights-cleared photo library, tagged | Recommended | Powers Content Creation AI and Brand & Collateral AI. Starts on the bundled sample library — see "Connect your systems." |
| A mailbox and/or a WhatsApp/webhook channel | Optional | Only used by Marketing Performance AI's exec report and ROAS alerts, off by default. |

Time estimate: 15 minutes to see the demo, half a day to connect real ad
performance exports and fill in your brand kit, a few days of watching the
review queue before you would reasonably consider going live.

## Quick start (5 minutes, no credentials)

```bash
git clone https://github.com/th1-ai/marketing-social-ai.git marketing-social-ai
cd marketing-social-ai
make setup
make demo
```

You should see something like this (campaign and design-request ids are
random each run, so yours will differ):

```
Marketing & Social AI demo - Hotel Aurora / The Marlow House, fixtures/hotel + fixtures/inbound

Suggestion queue (tools/run.py):

  8 suggestion(s) considered (8 queued, 0 skipped/muted).

Budget optimizer (tools/run.py --budget):

Note: Two ads stopped bleeding money this month: the junior suite push spent over nine thousand euros for zero bookings, and the breakfast terrace ad was running below break-even, so both are paused. The pool-evenings ad is outperforming its twin on click-through and picks up the shifted budget. Wine dinners keeps returning nearly nine times its spend on a small budget, so it scales up inside the safety cap, while the brand-search ad stays capped since its high return is a ceiling on demand, not room to grow.

  - Pulled 30-day funnels: 10 active ad(s), €44478.8 spent.
  - Ranked return: 0.0x to 59.0x.
  - Stopped the bleeding: 2 paused, €11191 freed.
  - Settled the A/B twins: 1 pair(s) rebalanced.
  - Fed the winners: 1 scaled up (2x inside the caps), 1 held (brand terms, demand-capped).
  - Drafted the order: 5 moves, projected +€20556/month. Nothing applies until you say so.

Content Creation AI - The Editor (tools/run.py --content):

  generated campaign <id> for suggestion <id> (12 creatives).
  Note: The campaign leans on the hot tub and spa treatment photography, with the apres-ski headline direction carrying the strongest emotional pull. Worth testing the staccato copy variant against the full-sentence version first, since it is the cheapest read on what actually lands.

Brand & Collateral AI - The Art Director (tools/run.py --design):

filed <id> - kind=poster, waiting for Brand & Collateral AI (`tools/run.py --design`) to draft it.
  drafted 1 design request(s).

Marketing Performance AI - The Attributor (tools/run.py --performance):

  exported data/exports/exec_report_2026-08-27.md
  1 ROAS-drop alert(s).

15 item(s) waiting for a person - nothing here ever auto-applies, see docs/safety.md.
Nothing was sent or posted: mode is shadow, and demo never calls ads.set_budget()/pause(), messaging.notify_staff(), or email.send() on anything but the fixtures.
Next: `make review` to see what is waiting, or read workflows/10-suggestions.md.

DEMO OK — 18 items processed, 18 drafted, 0 sent (shadow)
```

Every number above comes from an invented hotel, "Hotel Aurora" (plus a
second property, "The Marlow House," for the cross-property suggestion) —
ten sample ads, a tagged ten-photo library, six reviews, and two local
events, designed to exercise a pause, a twin rebalance, a scale-up, a hold,
a headline test, a review-quote ad, a landing-page callout, a
cross-property comparison, and all three sub-agents in one run, so you can
see exactly how this agent thinks before it ever touches your real
accounts. `make demo` force-enables all three sub-agents for this
walkthrough only; in a real run they stay off until you turn them on. Next:
open `claude` in this folder and follow "Set up with Claude Code" below.

Then `make doctor` — expect one `FAIL` (`hotel identity`, because the
property is still the shipped placeholder "Hotel Aurora") and a couple of
`warn` lines. That is the intended state of a fresh clone; see
`workflows/00-setup.md` for filling in the real property.

## Set up with Claude Code

Open `claude` in this folder. Paste each prompt below in order — Claude
will follow the named workflow file, which tells it exactly which tools to
run and what to check.

**Phase 1 — first run.**

> Read `workflows/00-setup.md` and walk me through it. I have not run this
> agent before.

**Phase 2 — the suggestion queue and the budget optimizer.**

> Read `workflows/10-suggestions.md` and `workflows/15-budget.md`. Run one
> pass of each and show me what the Bard found, in plain language.

**Phase 3 — the review queue.**

> Read `workflows/80-review.md`. Show me what is waiting for me, one at a
> time, and act on my decisions.

**Phase 4 — the sub-agents (only the ones you need).**

> Read `workflows/21-content-creation.md` (generate campaigns from a
> brief), `workflows/22-brand-collateral.md` (the brand kit and the
> design-request queue), and `workflows/23-marketing-performance.md`
> (ROAS-drop alerts and the Monday exec report). Help me turn on whichever
> ones apply to us.

**Phase 5 — going live.**

> Read `workflows/90-go-live.md`. Go through the checklist with me
> honestly — do not recommend going live until it is genuinely true.

You can also just run the agent directly — `/marketing-social-ai` in this
folder runs the suggestion queue and works through what needs you in one
command; see `.claude/skills/marketing-social-ai/SKILL.md`.

## Connect your systems

Full detail, including the "implement your own" recipe, is in
`docs/integrations.md`. This agent reads six JSON signal files, writes
through one new adapter this repo adds (**Ads**), and uses two of the four
shared core adapters — **Email** and **Messaging** — for exactly one thing
each.

### Signals — `data/imports/*.json`

| File | Status | Notes |
|---|---|---|
| `data/imports/ad_performance.json` | universal | Daily rows from Meta/Google Ads — export by hand or script it. No ad-platform API is called anywhere in this repo. |
| `data/imports/marketing_assets.json` | universal | Your ad catalogue: slug, kind, status, platform, daily_budget. |
| `data/imports/content_assets.json` | universal | Your brand kit: photos, logos, colours, fonts, voice docs. |
| `data/imports/content_performance.json` | universal | Blog/newsletter equivalent, if you have any. |
| `data/imports/reviews.json` | universal | Feeds the `review_ad` suggestion category. |
| `data/imports/events.json` | universal | Your own venue calendar or local-events feed — feeds `event_signal`. |

All six fall back to the bundled `fixtures/` when nothing is imported —
`make doctor`'s "signal sources" line shows which is which.

### Ads — `config/agent.yaml: ads.adapter`

| Adapter | Status | Needs | Notes |
|---|---|---|---|
| `mock` | built | nothing | Logs to `data/demo/ads_mock.jsonl`. What `make demo` uses. |
| `csv` | universal | nothing | Appends to `data/exports/ad_budget_changes.csv` for you to apply by hand. **Start here.** |
| `stub` | stub | — | Every write raises with a recipe. |

No ad platform's write API is called anywhere in this repo — see
`docs/integrations.md` for why, and the recipe for wiring up a real one.

### Email — `systems.email.adapter` in `config/hotel.yaml`

Used only for the Monday exec report, when Marketing Performance AI is on.

| Adapter | Status | Needs |
|---|---|---|
| `mock` | universal | nothing |
| `imap` | universal | mailbox + app password |
| `gmail` | built | Google OAuth desktop client |

### Messaging — `systems.messaging.adapter`

Used only for a ROAS-drop alert notify, when Marketing Performance AI is on.

| Adapter | Status | Needs |
|---|---|---|
| `mock` | universal | nothing |
| `unipile` | built | your own UniPile account |
| `webhook` | universal | any URL |

### Everything else

`pms`, `sheets`, `pos`, `accounting`, `reviews` (as a review-*platform*
integration, distinct from the `data/imports/reviews.json` signal above),
`calendar`, `payments`, `procurement` and `locks` exist in `core/` for
every repo in this family but are not called anywhere in this agent's own
`tools/` — attributed bookings are expected to arrive pre-joined into
`data/imports/ad_performance.json`, and GA4/Search Console are not wired
at all (see `docs/integrations.md`).

## Run it

```bash
make run                              # suggestion queue
make run ARGS="--budget"              # budget optimizer
make run ARGS="--content"             # Content Creation AI, once enabled
make run ARGS="--design"              # Brand & Collateral AI, once enabled
make run ARGS="--performance"         # Marketing Performance AI, once enabled
make run ARGS="--dry-run"             # compute everything, write nothing
make watch                            # keep the suggestion loop running on schedule
```

**Scheduling.** Every recurring job lives in `config/agent.yaml: schedule:`
with its own `command:` and `cadence:` — `suggestions` (daily),
`budget` (daily), `content_creation` (weekly), `brand_collateral`
(every 30 min), `marketing_performance` (Monday 09:00):

```bash
python3 tools/schedule.py --all
```

prints one ready-to-paste cron/launchd/systemd snippet per job, read
straight from that block. `scheduler/crontab.example`,
`scheduler/launchd.example.plist`, `scheduler/systemd.example.service` and
`scheduler/systemd.example.timer` have the generic single-job form if you
would rather hand-edit.

**Subscription or API.** `llm.provider: interactive` or `claude-code` runs
on the Claude Code subscription you already pay for — genuinely the
cheapest way to run this agent, since it calls a model at most three times
per pass (two narration notes, one copilot question), far below a
guest-facing agent's volume. `llm.provider: anthropic` uses your own API
key, bills per token, and is the right choice if you also run the copilot
heavily. Either way `make report` shows what you are actually spending.
See `docs/safety.md` for the full honest note.

## Go live

Shadow mode is the default and stays the default until you change it. The
full checklist — real properties and brand kit filled in, a real ads
adapter connected, a few days of real review behind you, the shadow
backlog cleared — is in `workflows/90-go-live.md`. In short:

```yaml
# config/hotel.yaml
mode: live
```

Going live means an **approved** item now actually acts — it does not
change what needs approval. Unlike some agents in this family, there is no
"guarded autopilot" tier to widen later: every suggestion, budget change,
design request, ROAS alert and exec report waits for a person, in shadow
and in live, forever. Before flipping the switch, clear the backlog that
built up in shadow mode — it was computed against yesterday's numbers:

```bash
python3 tools/review.py stale
```

Going back to shadow (`mode: shadow`, or `AGENT_MODE=shadow` in `.env` for
one run) stops every action immediately, mid-schedule, with no other
change required.

## Guardrails & safety

Full detail in `docs/safety.md`. The short version:

**What it will not do.**

- Act on anything while `mode: shadow` — including an item you already
  approved. The approval is recorded; acting waits for `mode: live`.
- Auto-apply a budget change, ever, in any mode. The roster's `cant` makes
  this promise unconditionally ("Won't post or move a budget without
  approval") and this repo holds every other kind — suggestions, design
  requests, ROAS alerts, the exec report — to the same bar.
- Compose a creative from anything outside the approved photo library and
  brand kit. There is no image generation at runtime.
- Scale an ad past the safety cap, or pause a cheap failing test — pausing
  needs both a return below the line **and** more than €900 spent in 30
  days.
- Take a payment or move money — no payment adapter exists in this agent
  at all.
- Invent an ad-performance number, a review quote, or an asset. The
  copilot's system prompt is explicit: "only state numbers that come from
  your tools."

**What always shows, whatever the config** (`config/agent.yaml: rules`,
enforced in `tools/budget_engine.py` and `tools/content_engine.py`):

- An off-brand draft, when `brand_guard` is off — labelled in three places:
  the spec, the label, and a corner flag — never silently.
- A brand-term ad (ROAS above `hold_roas_above`) held, never scaled — it is
  demand-capped, not room to grow.
- A muted `event_signal` suggestion, when `event_radar` is off — written
  straight to `skipped`, never shown as actionable.

**Guest-facing content, without a bundled disclosure line.** Every
creative, caption and headline this agent generates is a draft: a human
reviews it, a human pushes it to the library, and a human decides how to
disclose AI assistance on the finished post, following your own platform's
and jurisdiction's rules (EU AI Act Article 50 and similar). This repo does
not publish anything itself, so there is no signature line to auto-append
the way a guest-email agent in this family has one — see `docs/safety.md`
"Telling guests they are seeing AI-assisted content." No em dashes in any
copy a guest might see, whatever `llm.provider` writes — check drafts
before you push them.

**Data handling.** Everything lives in `data/agent.db` on your own
machine — there is no cloud service behind this repo. There is no guest
personal data anywhere in this agent's tables.

## Sub-agents in this repo

All three fold into this repo and are **off by default** — the suggestion
queue and the budget optimizer above are fully useful without any of them.
Full detail: `docs/sub-agents.md`.

### Content Creation AI — "The Editor"

**Does.** Turns the hotel's existing footage and photo library into finished content. It selects clips, edits them together, writes the captions and copy, and assembles ready-to-post videos and posts.

**Won't.** Won't publish without a human eye on brand and licensing; it produces the cut, you approve it.

Off by default — see `workflows/21-content-creation.md` to turn it on and
brief it. ROI: `-80%` content production cost (labor).

### Brand & Collateral AI — "The Art Director"

**Does.** Produces on-brand marketing collateral at portfolio scale — menus, social visuals, offer graphics, print pieces — each generated from the property's own brand kit (colours, type, logo rules) and routed through your design-request queue with a human approval step.

**Won't.** A designer approves before anything ships; it drafts at volume, it doesn't replace taste. Needs a brand kit per property to stay on-brand.

Off by default — see `workflows/22-brand-collateral.md` to turn on the
design-request queue; the brand kit itself (`tools/brand_kit.py show`) is
always on, no toggle needed. ROI: `-85%` design turnaround time (labor).

### Marketing Performance AI — "The Attributor"

**Does.** Unifies GA4, Google & Meta Ads, and Search Console with the PMS to tie every direct booking back to the campaign that produced it — true ROAS, not the ad platform's modeled number. Watches spend efficiency per property, alerts on ROAS drops, and distills it all into a Monday-morning executive read: ten dashboards, one two-minute email, no logins.

**Won't.** Doesn't move budgets itself — its numbers feed the budget desk, where changes apply only inside safety caps and with your approval. Attribution is only as good as the tracking it's given — it flags the gaps rather than papering over them.

Off by default — see `workflows/23-marketing-performance.md` to turn it
on. GA4 and Search Console are not wired anywhere in this repo; the exec
report's numbers are exactly what `data/imports/ad_performance.json`/
`data/imports/content_performance.json` carry. ROI: `-28%` wasted ad spend (revenue).

## Customising

**`config/agent.yaml`.** Your real `properties`, the six `rules` toggles,
every `budget:` threshold (pause line, scale line, twin pairs — declare
your own, the shipped pair is a sample), the `subagents` block, `schedule:`.

**`knowledge/marketing-policy.md`.** Read by the copilot and both
narration prompts — your voice, the claims you never make, the reasoning
behind your budget thresholds. See `knowledge/README.md`.

**`prompts/`.** `prompts/budget_note.md`, `prompts/campaign_note.md` and `prompts/copilot_ask.md`
are plain markdown with `{{var}}` placeholders — edit them to change tone.
They cannot change a number or a decision; only the words about one that
already happened.

**Adding a language.** The engine's own text (suggestion rationales, budget
reasons, and Content Creation AI's actual creative copy — headlines,
sublines, CTAs) is English-only in this template — it is generated by code,
not a model, so there is no language setting to flip. That includes a
freestyle brief you type in another language: `python3 tools/campaign.py
brief --freestyle` recognises the same subject/season/audience concepts in
Spanish, French, German, Italian and Portuguese as well as English (so
"quartos... para casais" still maps to rooms, not a wrong default), but the
12 creatives it drafts are still English copy. When the brief's own language
is one your `hotel.languages` actually lists, the campaign is drafted
anyway — never blocked — with a plain "captions are English, translate
before posting" flag, and a `needs_human` item is filed so it shows up in
`make review` rather than a line that scrolls off your screen. If the
subject itself can't be matched with confidence in any of the six
languages, the same thing happens rather than guessing which of spa / rooms
/ dining / offer you meant. Short of editing `tools/content_engine.py`'s
Python source, there is no supported way to get the actual creative copy
itself into another language — the copilot and the two narration notes
answer in whatever language you write the prompt files in; translate
`prompts/*.md` if you want those in another language.

**Twin pairs.** `config/agent.yaml: budget.twin_pairs` is a list of
`[loser_slug, winner_slug]` pairs you maintain — there is no automatic
A/B-twin detection. Add a pair once you have two ads genuinely testing the
same audience with a different creative.

## Troubleshooting & FAQ

Full list in `workflows/99-troubleshooting.md`. The most common ones:

**`make doctor` shows a FAIL.** Every line has a fix hint right under it —
read it before doing anything else. The "hotel identity" FAIL on a fresh
clone is expected.

**`make run ARGS="--budget"` exits with code 3.** Not an error —
`llm.provider: interactive` is waiting for you to answer the parked note
prompt in `data/pending/`. (`python3 tools/run.py --once --budget` itself
really does exit 3 — `make run` prints `make: *** [run] Error 3` in the
console, naming the real code, but Make's own exit status is always 2 for
any failed recipe, GNU Make's own convention, regardless of what the
command underneath exited with. Script against `python3 tools/run.py
--once` directly if you need the real number, not `make run`.) Every
budget decision was already made and queued before this happened.

**A suggestion or budget change never appears in the queue.** Everything is
keyed per calendar day — re-running the same day for a slug that already
has a decision changes nothing; see `docs/how-it-works.md` "Idempotency."
A `hold` budget row or a muted `event_signal` suggestion is there, just at
`skipped`, not lost.

**Can I run this without any ad spend at all?** The suggestion queue's
`review_ad`, `event_signal`, `cross_property` and `landing_page` categories
still work off `data/imports/ad_performance.json` rows even for a small account; the
budget optimizer needs at least one active ad with a `daily_budget` to do
anything.

**The suggestion queue is empty except events.** That is the honest answer
on a small or quiet fixture set, not a bug — `headline_test` needs a
creative old enough, `review_ad` needs a theme mentioned enough times. See
`docs/how-it-works.md`.

## Measuring the benefit

`make report` shows volumes, queue age, campaigns generated versus pushed,
a budget summary (paused/scaled/held), and LLM spend — all computed from
`data/agent.db`, nothing phoned home. See `docs/benefits.md` for what each
number means and the honest caveats before you quote any of this to
someone else.

```bash
make report
python3 tools/report.py --json
```

## About

Built by [TH1](https://th1.ai) — we build and run AI agents for
independent hotels. This repo is free to use, modify and self-host under
the MIT licence (see `LICENSE`).

Want it run for you, tuned to your property, with someone accountable for
the result? [Talk to TH1](https://th1.ai).

**Changelog**

- v1.0 — initial release: the suggestion queue, the budget optimizer,
  Content Creation AI, Brand & Collateral AI and Marketing Performance AI
  folded in, all three off by default.
