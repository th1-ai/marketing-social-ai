# Workflow: first-run setup

Objective: get Marketing & Social AI from a fresh clone to a working demo,
then to real config, in one sitting.

## Steps

1. **Install and check.**
   ```bash
   make setup
   make doctor
   ```
   `make setup` creates the virtualenv, installs `requirements.txt`, and
   copies `.env.example` -> `.env` and every `config/*.example.yaml` ->
   `config/*.yaml` (only if those files do not exist yet - it never overwrites
   your own copies). `make doctor` will show a `FAIL` on "hotel identity"
   right after setup - that is expected, it means the property name is still
   the shipped placeholder "Hotel Aurora." Everything else should be `ok` or
   `warn`.

2. **Run the demo.** No credentials needed.
   ```bash
   make demo
   ```
   Expect to see the suggestion queue reason through the fixtures, then the
   budget optimizer pause two ads and scale a third, then all three
   sub-agents (force-enabled for this walkthrough only), then the line
   `DEMO OK — 18 items processed, 18 drafted, 0 sent (shadow)`. If you do not
   see that, stop and read `workflows/99-troubleshooting.md` before going
   further.

3. **Fill in the property.** Edit `config/hotel.yaml` (name, address,
   currency, languages). Then `config/agent.yaml` — this is the important one
   for this agent: your real `properties` (one entry is fine for a single
   hotel), the six `rules` toggles, and the `budget:` thresholds. Twin pairs
   in particular are yours to declare — the shipped example
   (`aurora-adults-pool` / `aurora-pool-evenings`) does not exist once you
   replace the sample ads. See the comments in `config/agent.example.yaml`.

4. **Set up the brand kit.** This agent composes only from what
   `fixtures/hotel/content_assets.json` (or your own
   `data/imports/content_assets.json`) gives it — colours, fonts, logos,
   voice documents, and a tagged photo library. Run
   ```bash
   .venv/bin/python tools/brand_kit.py show
   ```
   to see what it currently reads. Replace the sample rows with your own
   before you enable Content Creation AI or Brand & Collateral AI — see
   `docs/integrations.md`.

5. **Feed the signals no ad platform's dashboard exposes as one file.** Ad
   performance, reviews and local events are not a PMS or an email field —
   they are your own JSON exports in `data/imports/`
   (`ad_performance.json`, `content_assets.json`, `reviews.json`,
   `events.json`). `make doctor`'s "signal sources" line shows which is
   reading from a real file and which is defaulting to the demo fixtures.
   Full field list: `docs/integrations.md`.

6. **Point the budget writes somewhere real.** `config/agent.yaml`'s
   `ads.adapter` starts as `mock` (writes nowhere real). Set it to `csv`
   (appends to `data/exports/ad_budget_changes.csv` for you to apply by hand
   in Meta Ads Manager / Google Ads) — see `docs/integrations.md`. Run
   `make doctor` after changing it.

7. **Pick how the agent thinks.** `config/hotel.yaml`'s `llm.provider` starts
   as `interactive` — it asks you, in this Claude Code session, instead of
   calling a model. That costs nothing extra, and the model is only ever
   used to write a short note about a run that already happened, or to
   answer one grounded copilot question — see `docs/safety.md` for why that
   is safe by construction.

8. **Decide on the three sub-agents.** `config/agent.yaml`'s `subagents`
   block: `content_creation`, `brand_collateral` and `marketing_performance`
   all start **off** — the suggestion queue and the budget optimizer are
   fully useful without any of them. See `workflows/21-content-creation.md`,
   `workflows/22-brand-collateral.md` and `workflows/23-marketing-performance.md`.

9. **Re-check.**
   ```bash
   make doctor
   ```
   Once the property name is real and the brand kit is your own, the "hotel
   identity" and "signal sources" lines turn green. Move on to
   `workflows/10-suggestions.md` to run the loop for real.
