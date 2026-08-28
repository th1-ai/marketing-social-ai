# Sub-agents in this repo

All three fold into this repo, all three are **off by default** — the
suggestion queue (`workflows/10-suggestions.md`) and the budget optimizer
(`workflows/15-budget.md`) do the Bard's whole job without any of them. No
coach layer applies to this agent (see the brief): there is no free-text
guest reply for a human to edit and re-teach; every decision here is a
number or a generated draft a human approves, edits at the source, or
rejects.

## Content Creation AI — "The Editor"

**Does.** "Turns the hotel's existing footage and photo library into
finished content. It selects clips, edits them together, writes the
captions and copy, and assembles ready-to-post videos and posts."

**Won't.** "Won't publish without a human eye on brand and licensing; it
produces the cut, you approve it."

**Output.** "Produces several ready-to-post videos and posts a week from
footage you already own." ROI: `-80%` content production cost (labor).

**In this repo.** `tools/content_engine.py` + `tools/campaign.py`, toggled
by `config/agent.yaml: subagents.content_creation.enabled`. Run it by hand
with `python3 tools/campaign.py brief ...`
(`workflows/21-content-creation.md`), or automatically with `make run
ARGS="--content"` against approved `event_signal`/`new_creative`
suggestions. It scores your photo library against the brief (property,
subject, season match, minus a season mismatch penalty, plus a hero bonus),
composes 12 creatives from a copy bank rotated across 3 layouts and 2
treatments, and plans a 4-shot video sequence — the same mechanism the
source demo runs, minus its build-time-only rendered MP4 (see
`docs/how-it-works.md`).

**The one honest gap.** The roster says it "selects clips" from "existing
footage." This template works entirely from stills — there is no video
ingest anywhere, in the source demo or here. Turning it on gets you 12
finished creative directions and a shot-by-shot video plan you could hand
to an editor; it does not cut a video file for you.

## Brand & Collateral AI — "The Art Director"

**Does.** "Produces on-brand marketing collateral at portfolio scale —
menus, social visuals, offer graphics, print pieces — each generated from
the property's own brand kit (colours, type, logo rules) and routed through
your design-request queue with a human approval step."

**Won't.** "A designer approves before anything ships; it drafts at
volume, it doesn't replace taste. Needs a brand kit per property to stay
on-brand."

**Output.** "Routine collateral turned around in hours instead of weeks, at
a fraction of agency cost." ROI: `-85%` design turnaround time (labor).

**In this repo.** `tools/brand_kit.py` (the standing, always-on constraint
layer — no toggle, no run loop, matches the source: "the content the AI is
allowed to compose from") plus `tools/design_engine.py` and
`tools/design_requests.py`, the design-request queue itself, toggled by
`config/agent.yaml: subagents.brand_collateral.enabled`
(`workflows/22-brand-collateral.md`). File a request, `make run
ARGS="--design"` drafts it against the same brand kit and photo scoring the
Editor uses, a designer approves or rejects it in
`workflows/80-review.md`.

**The one honest gap.** The source demo has no design-request queue at all
— this repo built the v1 its own spec called for: `requested_by` / `brief`
/ `due` / a status that reaches `pending_review`. Production (printing,
uploading to a channel) stays a human step this repo does not model, same
as the source.

## Marketing Performance AI — "The Attributor"

**Does.** "Unifies GA4, Google & Meta Ads, and Search Console with the PMS
to tie every direct booking back to the campaign that produced it — true
ROAS, not the ad platform's modeled number. Watches spend efficiency per
property, alerts on ROAS drops, and distills it all into a Monday-morning
executive read: ten dashboards, one two-minute email, no logins."

**Won't.** "Doesn't move budgets itself — its numbers feed the budget desk,
where changes apply only inside safety caps and with your approval.
Attribution is only as good as the tracking it's given — it flags the gaps
rather than papering over them."

**Output.** "True campaign-level ROAS per property, drop alerts within a
day, and a Monday 9 AM exec report that replaces hours of manual
reporting." ROI: `-28%` wasted ad spend (revenue).

**In this repo.** `tools/attribution_engine.py`, toggled by
`config/agent.yaml: subagents.marketing_performance.enabled`
(`workflows/23-marketing-performance.md`). `make run ARGS="--performance"`
compares each creative's trailing 7-day ROAS to the 7 days before it and
raises an alert past a configured threshold, then composes and exports a
markdown exec report every pass and, once approved and `mode: live`, emails
it to `contacts.manager`.

**The one honest gap.** The source has "concept" status and genuinely no
engine of its own — this repo built the ROAS-drop alert and the exec report
from scratch, since nothing existed to adapt beyond the funnel-bar UI
pattern. GA4 and Search Console are not wired anywhere — the numbers this
agent reports are exactly what `ad_performance.json`/
`content_performance.json` carry, real but narrower than the roster's "ten
dashboards" until those feeds exist.

## The shared thread

None of the three ever moves money or posts anything on its own. Content
Creation AI generates drafts a human pushes to a library. Brand & Collateral
AI drafts collateral a designer approves. Marketing Performance AI reports
numbers that feed the budget desk, which is the only thing in this repo
that can act on them — and even the budget desk always waits for a person.
