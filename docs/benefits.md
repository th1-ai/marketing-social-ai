# The business case

## The problem this agent solves

Marketing at a small or mid-size property is usually one person's spare
time: a suggestion for a new ad sits in someone's head instead of a queue, a
budget that should have been paused three weeks ago is still spending, and
"we should turn that good review into an ad" never happens because nobody
has an hour to sit down and do it. This agent keeps a standing, evidence-
backed queue of ideas, watches ad spend daily instead of monthly, and turns
a brief into 12 finished creatives in the time it takes to type the brief.

## What the roster promises

Quoted verbatim from `specs/agents.json` (also in `README.md` section 2):

- **Marketing & Social AI**: `+300%` content output (revenue). "3-5x content
  cadence plus ad budgets tuned continuously - waste paused in days, winners
  scaled inside caps."
- **Content Creation AI**: `-80%` content production cost (labor).
  "Produces several ready-to-post videos and posts a week from footage you
  already own."
- **Brand & Collateral AI**: `-85%` design turnaround time (labor).
  "Routine collateral turned around in hours instead of weeks, at a
  fraction of agency cost."
- **Marketing Performance AI**: `-28%` wasted ad spend (revenue). "True
  campaign-level ROAS per property, drop alerts within a day, and a Monday
  9 AM exec report that replaces hours of manual reporting."

## What to measure

`make report` / `tools/report.py`, reading straight from `core.store`:

- **Volumes**: items by kind (`suggestion`, `budget_change`, `design_request`,
  `roas_alert`, `exec_report`) and by review status right now.
- **Queue age**: how long the oldest pending item has waited — the thing
  `store.mark_stale()` protects against, and a proxy for whether the queue
  is actually being worked.
- **Campaigns**: how many campaigns Content Creation AI has generated, and
  how many drafts have been pushed to the library versus still sitting as
  `generated` — the "3-5x content cadence" claim, made concrete.
- **Budget summary**: how many ads paused, scaled up, or held across every
  budget run so far — the "waste paused in days, winners scaled inside
  caps" claim.
- **Spend**: LLM calls, tokens and cost, from `core.llm`'s usage logging.
  Two narration notes and (optionally) one copilot answer per pass — this
  agent's own model spend is small next to a guest-facing agent's.

Beyond `tools/report.py`, the honest measure of the budget optimizer's
value is the `projected_monthly_delta` printed at the end of every
`--budget` pass and recorded in each run's `runs.stats_json` — the sum of
every pause's freed spend and every scale-up's projected return, before a
human even opens the queue.

## Honest caveats

- **The suggestion queue is a heuristic, not a forecast.** Every category
  fires off a real number crossing a real threshold, but "worth doing" and
  "worth doing right now" are still a human's call — that is why nothing
  auto-approves.
- **The budget optimizer's `projected_delta_monthly` is a projection**, not
  a guarantee: it assumes the same conversion behaviour continues at the
  new spend level, which is not always true, especially for a steep scale-up.
- **Content Creation AI works from stills, not footage.** The roster says
  "selects clips, edits them together" — this template composes from
  photography only; a real video-ingest pipeline is future work
  (`docs/how-it-works.md` "Design decisions" #1 in the source spec).
- **"Portfolio scale" is not modelled.** Every pass here is one property at
  a time. Batch generation across a portfolio (the roster's `cross_property`
  suggestion category aside) is future work.
- **The exec report has no GA4 or Search Console behind it.** Its numbers
  are what `ad_performance.json`/`content_performance.json` actually carry
  — real, but narrower than "ten dashboards" until those feeds are wired
  in.
