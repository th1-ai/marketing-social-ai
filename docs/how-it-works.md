# How Marketing & Social AI works

One standing suggestion queue, one deterministic budget optimizer, and three
folded-in sub-agents that read the same brand kit and performance numbers.
Every decision a human sees traces back to a plain function in `tools/*.py`
you can read end to end — **deterministic decisioning, LLM for language**,
the same split every agent in this family uses. The only places a model
runs are the marketing copilot (`tools/copilot.py`) and two cosmetic notes
written after a run has already finished; nothing here lets a model choose
what happens to a euro of ad spend or what ships to a guest's feed.

## The main loop (`tools/run.py`)

```mermaid
flowchart TD
    A[ingest: ad performance, content assets, reviews, events] --> B{which pass}
    B -- default --> C[suggestion_engine: generate the queue]
    B -- --budget --> D[budget_engine: analyse_budget]
    B -- --content, Editor on --> E[content_engine: generate_campaign for approved briefs]
    B -- --design, Art Director on --> F[design_engine: draft queued design requests]
    B -- --performance, Attributor on --> G[attribution_engine: ROAS-drop alerts + exec report]
    C --> H[items: pending_review / skipped]
    D --> H
    F --> H
    G --> H
    H --> I[review queue - workflows/80-review.md]
    I -- approve --> J[tools/review.py send: apply, notify, or just close out]
    E --> K[campaigns/creative_drafts table - a gallery, not a queue]
    K -- push to library --> L[marketing library export]
```

**Ingest** (`tools/ingest.py`). Ad performance, the brand kit (photos,
colours, fonts, voice docs), reviews and local events are not things a PMS
or an email inbox exposes — see "Design decisions" #1. They come from
`data/imports/*.csv`/`*.json` (your own export) with a `fixtures/` fallback
for `make demo` and the tests, exactly the shape `revenue-management-ai`
uses for pace and comp rates.

**The suggestion queue** (`tools/suggestion_engine.py`, no flag). The
standing surface: event radar, headline tests, review-quote ads,
cross-property plays and landing-page callouts, each generated from a real
number in the ingested data with the evidence attached. An `event_signal`
suggestion is muted (written straight to `skipped`, never shown as
actionable) when `rules.event_radar` is off — see "Design decisions" #2.

**The budget optimizer** (`tools/budget_engine.py`, `--budget`). A direct
port of the source engine's three-phase pass: pause the bleeders, settle
the configured A/B twin pairs, feed the winners inside the safety cap. Read
"The budget steps" below for the exact thresholds. **Nothing here ever
auto-applies** — every proposal is written `pending_review`, whatever
`autonomy` says, because the roster's `cant` is unconditional ("Won't post
or move a budget without approval"), stronger than the guarded/full
autopilot other agents in this family offer. `hold` rows (brand-term ads,
ROAS > 20) go straight to `skipped` — informational, never actioned.

**Content Creation AI** (`tools/content_engine.py`, `--content`, off by
default). Generates 12 on-brand creatives and a 4-shot video plan from a
brief — either one a human types with `tools/campaign.py brief`, or one an
approved `event_signal`/`new_creative` suggestion pre-filled (mirroring the
source's "approve an event suggestion, the Studio brief pre-fills" flow).
Campaigns live in their own table, not the review queue — see "Design
decisions" #3.

**Brand & Collateral AI** (`tools/design_engine.py` + `tools/brand_kit.py`,
`--design`, off by default). `tools/brand_kit.py show` is the read-only
standing constraint layer (no run loop, matches the source: colours, fonts,
logos, voice docs). `--design` is the design-request queue the roster
promises but the source never built — see "Design decisions" #4. It drafts
each open request against the same brand kit and photo scoring the Editor
uses, then waits for a designer's approval.

**Marketing Performance AI** (`tools/attribution_engine.py`, `--performance`,
off by default). Aggregates the same ad-performance rows the budget
optimizer reads (CTR, ROAS, CPC, CPM, CVR), raises a `roas_alert` item when
a creative's trailing week drops more than `roas_drop_alert_pct` against
the week before, and on the configured day composes the Monday-morning
exec report — a short markdown digest, always exported to
`data/exports/`, and emailed to `contacts.manager` when approved and
`mode: live`.

**Review and narrate.** `workflows/80-review.md` is the one queue for
suggestions, budget changes, design requests and ROAS alerts alike.
`tools/review.py send` dispatches by item kind — a budget change calls the
ads adapter, a ROAS alert notifies staff, a suggestion or design request
just closes out (approval *is* the action; nothing further leaves the
building). The budget pass calls `core.llm.complete()` once, after the
proposals are final, for a three-sentence note — see `prompts/budget_note.md`.
Campaign generation gets the same treatment via `prompts/campaign_note.md`.
Both fall back to a deterministic sentence if the model call fails; neither
blocks the run.

## The budget steps (`analyse_budget`)

Ported from the source engine, unchanged, with the config knobs named in
`config/agent.example.yaml: budget`:

1. **Snapshot.** Every active ad with a daily budget, aggregated over the
   last 30 days into spend, revenue, ROAS, CTR.
2. **Read the safety cap.** Cap on: scale factor 2, pause line ROAS < 1.0.
   Cap off: scale factor 3, pause line ROAS < 1.5. The step log says
   "OUTSIDE the safety caps" in red when it is off.
3. **Order by spend**, descending. A `handled` set guarantees one row per ad.
4. **Phase 1 — stop the bleeding.** ROAS under the pause line **and** more
   than €900 spent in 30 days → pause. The reason branches on zero bookings
   ("zero attributed bookings — pause and rebuild the creative") versus a
   below-the-line return ("N.N× return after €X spend").
5. **Phase 2 — settle the twins.** Configured `twin_pairs` (loser, winner);
   skipped unless the winner beats the loser by at least `twin_roas_gap_min`
   (2.0×). Shifts `twin_shift_pct` (40%) of the loser's budget to the winner,
   rounded to the nearest €5.
6. **Phase 3 — feed the winners**, same spend order, unhandled ads only.
   ROAS > 20 → hold (brand-term, demand-capped, never scaled). ROAS ≥ 7 and
   daily budget ≤ €200 → scale up by the safety-cap factor. Everything else
   is left alone.
7. **Summary.** Freed monthly (sum of pause deltas), projected monthly delta
   (sum of all deltas), proposal count, whether the caps are off.

## Design decisions taken where the spec was open

1. **No adapter exists for an ad platform, a DAM, or GA4/Search Console.**
   `core/adapters/` covers PMS, email, messaging and sheets — none of those
   is "Meta Ads" or "your photo library." Ad-performance rows, the brand
   kit, reviews and events are ingested from `data/imports/` (your own
   export) with a `fixtures/` fallback. Budget writes go through
   `tools/ads_adapters.py` (`mock` / `csv` / `stub` — see
   `docs/integrations.md`), a **core request** noted in the build report:
   promote it into `core/adapters/__init__.py`'s registry once a real
   Meta/Google Ads client exists for the family.
2. **Event radar's data source is your own events file.** The source seeds
   two rows by hand; this repo reads `data/imports/events.json` (your venue
   calendar or a script pointed at a local events feed), falling back to
   `fixtures/inbound/events.json` for the demo. Muting is enforced in code,
   not just in a UI: a muted suggestion never reaches `pending_review`.
3. **Campaigns are a gallery, not a review-queue item.** The source's
   "Push to library" is a direct human action, not an approve/reject
   decision — pushing a draft into the library never talks to a live ad
   platform, so it does not go through `core.review`'s write guard. Only
   the budget change that would actually spend money, and the exec report
   that would actually leave an inbox, are guarded writes.
4. **The design-request queue is built, not just documented.** The source
   has no table, no statuses, no assignee for "routed through your
   design-request queue with a human approval step" — this repo's own open
   question. `tools/design_requests.py new` files one; `--design` drafts it
   against the brand kit; a designer approves or rejects it in
   `workflows/80-review.md`. Production (print, upload) stays a human step,
   same as the source.
5. **Twin pairs are config, not a hard-coded constant.** The source's
   `TWIN_PAIRS` is one line in a TypeScript file. `config/agent.yaml:
   budget.twin_pairs` is a list you maintain — the honest answer to the
   source's own open question #4 (no automatic A/B-twin detection exists
   anywhere to port).
6. **The ±50%/PLAN-vs-engine mismatch is resolved in the engine's favour.**
   The source's plan document said "max ±50%/day"; its shipped engine
   scales ×2 (cap on) or ×3 (cap off). This repo keeps the shipped
   behaviour — it is what the promise "waste paused in days, winners scaled
   inside caps" actually describes — and both factors are config, not a
   constant, so you can dial them to your own risk tolerance.
7. **ROAS-drop alerting is new.** The source names it in the roster
   (`does`: "alerts on ROAS drops") but built no mechanism. This repo
   compares each creative's trailing-7-day ROAS against the 7 days before
   it and raises a `roas_alert` item past `roas_drop_alert_pct` (25% by
   default) — a plain, explainable threshold, not a statistical model.
8. **The Monday exec report is new.** No template, schedule or recipient
   existed to adapt. `tools/attribution_engine.py:build_exec_report()`
   composes the KPI strip, the week's biggest mover, and every open item
   waiting in the queue into one markdown digest, exported every run and
   emailed on the configured day once approved and live.
9. **The copilot is one grounded turn, not a six-tool loop.** The source's
   `/api/marketing-chat` runs up to six tool round-trips against a live
   database. `tools/copilot.py` builds the same kind of compact, factual
   context (ad performance aggregates, a review search) in one pass and
   asks a single schema-constrained question — simpler, but the same
   "DATA TRUTHFULNESS: only state numbers that come from your tools" rule
   applies, and it can still file a suggestion.
10. **Variation generation keeps the source's cheapest-first order** (CTA
    colour, then background treatment, then one-word copy tests, then up to
    two photo swaps, then a video cut) but drops the source's off-brand
    colourway set — a template ships with the brand guard always on;
    turning it off in your own config still labels every off-brand draft
    three ways, it just never explores neon colours nobody asked for.
11. **PMS is not wired.** Attributed bookings and revenue arrive pre-joined
    into `ad_performance.json`, the same as in the source. A real booking
    join is future work for whoever adds a PMS adapter here — not this
    template's job.
12. **Every kind in this agent is draft-only — there is no auto-send path
    at all.** Other repos in this family have a "guarded" autopilot tier
    that lets a low-risk change through without a human. This agent does
    not: budget changes, suggestions, design requests and ROAS alerts all
    land at `pending_review` (or `skipped` when they are informational —
    a muted event suggestion, a `hold` budget row), never `auto_sent`. The
    roster's `cant` makes this promise unconditionally for budget moves
    ("Won't post or move a budget without approval"); this repo holds
    every other kind to the same bar rather than inventing a lower one.
13. **Content Creation AI never silently guesses.** COPY_BANK (the actual
    headline/subline/CTA copy `tools/content_engine.py` composes with) is
    English-only. `parse_freestyle()` recognises the same subject/season/
    audience concepts in Spanish, French, German, Italian and Portuguese
    too (accent-folded), so a brief like "quartos... para casais" maps to
    `subject: rooms`, not the old silent fallback to `offer` — but the
    campaign it drafts is still English copy. Two cases raise
    `CampaignResult.needs_human` rather than shipping the guess quietly:
    the brief's own detected language is one the hotel actually operates
    in (`hotel.languages`) but is not English (captions need translating
    before posting), or the subject could not be matched with confidence
    in any of the six languages (defaulted, not detected). Either way the
    campaign is still drafted — never blocked — and `tools/campaign.py`
    files a `suggestion`-kind item straight at `needs_human` with the
    reason, reusing the existing queue rather than adding a sixth kind, so
    `make review` surfaces it instead of a console line nobody reads back.
    See README "Adding a language" and `workflows/21-content-creation.md`.

## What runs when

| Workflow | Cadence | Provider used |
|---|---|---|
| `workflows/10-suggestions.md` (`tools/run.py`) | daily | none — the queue itself is deterministic |
| `workflows/15-budget.md` (`tools/run.py --budget`) | daily | only for the note |
| `workflows/21-content-creation.md`, off by default | weekly | only for the note |
| `workflows/22-brand-collateral.md`, off by default | every 30 min | none |
| `workflows/23-marketing-performance.md`, off by default | Monday 09:00 | none |
| `workflows/80-review.md` (`tools/review.py`) | whenever a human is available | none |
| `workflows/90-go-live.md` | once, then as needed | none |

No coach layer applies to this agent (see the brief) — there is no
free-text guest reply for a human to edit and re-teach; every decision here
is a number or a generated draft a human approves, edits at the source
(the brief, the config), or rejects.

## Idempotency

- **Suggestions** are keyed `(kind="suggestion", unique_key=slug)` —
  `upsert_unique` means re-running the generator the same day never
  duplicates a row; a changed underlying number updates the existing row's
  payload without disturbing a human's in-progress review.
- **Budget changes** are keyed `(kind="budget_change",
  "{run_date}:{asset_slug}:{action}")`. A re-run the same day is a no-op for
  anything already queued.
- **ROAS alerts** are keyed `(kind="roas_alert", "{run_date}:{asset_slug}")`.
- **Design requests** are created once by `tools/design_requests.py new`
  (a UUID key) and drafted at most once by `--design` — a second `--design`
  pass skips anything already past `new`.
- **Sends are claimed atomically.** `store.claim_for_send()` flips
  `approved`/`edited` to `sending` in one conditional `UPDATE`, the same
  guarantee every repo in this family gets from `core.store`.
- **`--dry-run` never advances state.** Nothing is written to the campaigns
  table, the items table, or an external system while `--dry-run` is set,
  even in live mode.
- **`store.mark_stale()`** ages out anything left un-reviewed for 72 hours
  so the queue cannot silently grow forever.

## Sub-agents in this repo

All three are **off by default** — the suggestion queue and the budget
optimizer are the parent's own loop and need none of them. `docs/sub-agents.md`
has the full detail per child.

- **Content Creation AI ("The Editor")** — `tools/content_engine.py`.
- **Brand & Collateral AI ("The Art Director")** — `tools/design_engine.py`
  + `tools/brand_kit.py`.
- **Marketing Performance AI ("The Attributor")** —
  `tools/attribution_engine.py`.

## Where core stops and this agent starts

`core/` is byte-identical to `factory/core/`. Everything in `tools/`,
`prompts/`, `fixtures/`, `workflows/`, `config/agent.example.yaml` and
`knowledge/marketing-policy.example.md` is this agent's own.
