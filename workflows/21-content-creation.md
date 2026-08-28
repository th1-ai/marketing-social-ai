# Workflow: Content Creation AI ("The Editor")

Objective: turn a brief — typed by hand, or pre-filled by an approved
`event_signal`/`new_creative` suggestion — into 12 on-brand creatives and a
4-shot video plan, composed only from your own photo library and brand kit.
Off by default; see `docs/sub-agents.md`.

## Turning it on

```yaml
# config/agent.yaml
subagents:
  content_creation:
    enabled: true
```

## Briefing it by hand

```bash
python3 tools/campaign.py brief --freestyle "Winter spa push for couples"
python3 tools/campaign.py brief --subject spa --property hotel-aurora \
    --season winter --audience couples
```

Guided mode needs all four of `--subject` (`spa|rooms|dining|offer`),
`--property`, `--season` (`winter|summer|autumn|spring`) and `--audience`
(`couples|families|business|wellness`). Freestyle mode keyword-maps one
sentence onto the same four fields, in English, Spanish, French, German,
Italian or Portuguese — see `docs/how-it-works.md` if a brief maps
somewhere unexpected.

**A non-English brief still gets an English campaign — flagged, not
silent.** The 12 creatives always come from the English-only `COPY_BANK`
(see README "Adding a language"). Write the brief in Portuguese and the
subject still maps correctly (`quartos` → rooms), but the campaign it
drafts is flagged: the console prints "needs a human", and a `suggestion`
item lands at `needs_human` in `make review` with the reason — "captions
are English, translate before posting." The same happens if the subject
can't be matched with confidence in any of the six languages at all —
this agent asks rather than guessing which of spa / rooms / dining / offer
you meant.

## The automatic pass

```bash
make run ARGS="--content"
```

Scans approved suggestions of category `event_signal` or `new_creative` that
do not have a campaign yet, and generates one for each — the same "approve
the event suggestion, the brief pre-fills" flow the source demo shows.
Nothing is pushed to the library automatically; that is always a human step.

## Reviewing and pushing a draft

```bash
python3 tools/campaign.py list
python3 tools/campaign.py show <campaign_id>
python3 tools/campaign.py push <campaign_id> <index>
```

`show` prints every draft's spec (photo, layout, treatment, headline,
subline, CTA, and whether it is flagged off-brand) plus the video plan.
`push` moves one draft into the creative library as `status='draft'` — this
never calls an ad platform and never goes through the review guard, because
it is an internal organizing step, not an external write (see
`docs/how-it-works.md` "Design decisions" #3). A human still has to launch
it for real in Meta Ads Manager / Google Ads.

## Generating variations from a winner

```bash
python3 tools/campaign.py variations <campaign_id> <draft_index>
```

Cheapest tests first: CTA colour, background treatment, one-word copy
changes, up to two photo swaps, one video cut — capped at 11 images plus the
video when `rules.variation_cap` is on.

## Edge cases

- **The photo library returns nothing.** `pick_photos` needs at least one
  `type: photo` row with a `url`; an empty library produces an empty
  campaign (0 creatives) rather than guessing.
- **The brief is in a language the copy bank can't caption, or the subject
  is unclear.** See above — the campaign still drafts, but
  `python3 tools/campaign.py list` shows `[needs_human]` next to it and the
  reason is in `python3 tools/campaign.py show <id>`'s `flag_reason`, as
  well as in the filed review-queue item.
- **`brand_guard` is off.** Every 4th draft in a fresh campaign is marked
  `off_brand` in three places: the spec, the label, and a note in the
  console output — never silently.
- **Determinism.** `generate_campaign`/`generate_variations` are pure
  functions — the same brief and the same library always produce the same
  12 drafts, byte for byte (`tests/test_content_engine.py` checks this
  directly).
