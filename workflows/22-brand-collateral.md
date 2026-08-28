# Workflow: Brand & Collateral AI ("The Art Director")

Objective: own the brand kit everything else composes from, and clear the
design-request queue — routine collateral drafted against your colours,
fonts, logo rules and photo library, with a designer's approval before
anything ships. Off by default; see `docs/sub-agents.md`.

## The standing brand kit (no run loop, no toggle needed)

```bash
python3 tools/brand_kit.py show
python3 tools/brand_kit.py show --property hotel-aurora
```

Read-only, always on. This is what `tools/content_engine.py` and
`tools/design_engine.py` score every photo and every colourway against.
Edit `fixtures/hotel/content_assets.json` (or your own
`data/imports/content_assets.json`) to give it your own kit.

## Turning the design-request queue on

```yaml
# config/agent.yaml
subagents:
  brand_collateral:
    enabled: true
```

## Filing a request

```bash
python3 tools/design_requests.py new --brief "Terrace poster for the derby" \
    --kind poster --property hotel-aurora --season summer --subject offer \
    --requested-by "Front office" --due 2026-09-10
python3 tools/design_requests.py list
```

`--kind` is one of `social | poster | menu | offer_graphic` — each maps to
its own layout (`docs/how-it-works.md` "Design decisions" #4). A request
sits at `new` until drafted.

## The automatic pass

```bash
make run ARGS="--design"
```

Drafts every open request against the brand kit and the same photo scoring
the Editor uses, then queues it at `pending_review`.

## Reviewing and approving

```bash
make review
python3 tools/review.py show <id>
python3 tools/review.py approve <id>
python3 tools/review.py reject <id> --reason "wrong photo, try again"
python3 tools/review.py send
```

Approval is the terminal step in this template — a designer's yes is the
"human approval step" the roster promises. Production (printing, uploading
to a channel) is a human task this repo does not model, same as the source
demo.

## Edge cases

- **No photo matches the request.** The draft ships with `creative: null`
  and a note that a designer needs to pick the shot by hand — never a
  guessed or generated image.
- **`brand_guard` is off.** The draft is still produced, marked `off_brand`,
  and the note says so plainly.
- **"Portfolio scale" is not modelled.** This is one property, one request
  at a time — batching the same brief across a portfolio is future work, see
  `docs/how-it-works.md`.
