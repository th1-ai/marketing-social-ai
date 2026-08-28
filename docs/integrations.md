# Connecting your systems

Every connector in this repo is one of three things, and the table says which.
We will not tell you an integration exists when it does not.

| Badge | Means |
|---|---|
| **built** | Written against the real API and tested against it. |
| **universal** | Works with any system through a common protocol: JSON/CSV, IMAP/SMTP, a webhook. |
| **stub** | Interface only. Calling it raises a clear error with a recipe for adding it. |

Check what is actually working on your machine at any time:

```bash
make doctor
```

## What this agent actually uses

Unlike a guest-facing agent, Marketing & Social AI does not read a PMS or a
guest inbox. Its inputs are ad performance, a brand kit, reviews and local
events (all JSON, ingested by `tools/ingest.py`); its outputs are a budget
write (a new adapter this agent adds, `tools/ads_adapters.py`), a staff
notification, and an emailed exec report.

### Signals - `data/imports/*.json`

| File | Reads | Notes |
|---|---|---|
| `ad_performance.json` | asset_slug, date, impressions, clicks, landing_views, bookings, spend, revenue | Daily rows. No ad-platform API is called anywhere in this repo — export from Meta Ads Manager / Google Ads and drop the file in `data/imports/`. Falls back to `fixtures/inbound/ad_performance.json`. |
| `marketing_assets.json` | slug, kind (`meta_ad`/`google_ad`), name, headline, status, platform, property, category, daily_budget, age_days | Your ad catalogue — the suggestion queue and the budget optimizer both read this. Falls back to `fixtures/hotel/marketing_assets.json`. |
| `content_assets.json` | photos, logos, colours, fonts, voice docs | Your brand kit — `tools/brand_kit.py show`. Photo `url`/`thumb_url` should point at your own rights-cleared library (any public bucket). Falls back to `fixtures/hotel/content_assets.json`. |
| `content_performance.json` | asset_slug, month, views, opens, clicks, bookings, revenue | Blog/newsletter equivalent of ad performance, if you have any. Falls back to `fixtures/inbound/content_performance.json`. |
| `reviews.json` | id, source, rating, review_date, themes[], body | Feeds the `review_ad` suggestion category. Export from your review platform, or hand-tag a CSV. Falls back to `fixtures/inbound/reviews.json`. |
| `events.json` | slug, name, start_date, end_date, when, rationale, impact | Your own venue calendar or a local-events feed — feeds `event_signal`. Falls back to `fixtures/inbound/events.json`. |

`make doctor`'s "signal sources" line shows which of these is reading a real
file versus the demo fixtures.

### Ads - `config/agent.yaml: ads.adapter`

| Adapter | Status | Needs | Notes |
|---|---|---|---|
| `mock` | built | nothing | Logs to `data/demo/ads_mock.jsonl`. What `make demo` uses. |
| `csv` | universal | nothing | Appends to `data/exports/ad_budget_changes.csv` for you to apply by hand in Meta Ads Manager / Google Ads. **Start here for a real run.** |
| `stub` | stub | — | Every write raises with a recipe. |

**No ad platform's write API is called anywhere in this repo.** Meta Ads and
Google Ads both have their own auth model and neither exposes a shared
"set daily budget" shape the way PMS vendors roughly agree on reservations —
see `docs/how-it-works.md` "Design decisions" #1. This is a **core request**
noted in the build report: promote a real Meta/Google Ads client into
`core/adapters/__init__.py`'s registry once one exists for this family. To
build your own now, copy `tools/ads_adapters.py`'s shape (`AdsMock`/`AdsCsv`
subclassing `core.adapters.base.Adapter`, `@guarded_write("apply_budget_change")`
on every write) and wire it into `tools/ads_adapters.py:get_ads()`.

### Email - `systems.email.adapter`

Used for exactly one thing: the Monday exec report, when Marketing
Performance AI is on and `contacts.manager.email` is set.

| Adapter | Status | Needs | Notes |
|---|---|---|---|
| `mock` | universal | nothing | Logs the send, sends nowhere real. |
| `imap` | universal | mailbox + app password | Any provider. **Start here.** |
| `gmail` | built | Google OAuth desktop client | |

```
EMAIL_ADDRESS=reservations@example.com
EMAIL_PASSWORD=            # an APP password, never your login password
IMAP_HOST=imap.example.com
SMTP_HOST=smtp.example.com
SMTP_PORT=587              # 587 STARTTLS, 465 implicit TLS
```

### Messaging - `systems.messaging.adapter`

Used for exactly one thing: a ROAS-drop alert notify, when Marketing
Performance AI is on.

| Adapter | Status | Needs | Notes |
|---|---|---|---|
| `mock` | universal | nothing | Logs the notify, sends nowhere real. |
| `unipile` | built | your own UniPile account | WhatsApp on your own number. |
| `webhook` | universal | any URL | POST to Zapier, Make, n8n, or your own endpoint. |

### PMS, Sheets, GA4, Search Console

**Not wired in this agent.** Attributed bookings/revenue are expected to
arrive pre-joined into `ad_performance.json` from whatever already ties your
ad platforms to your PMS — this agent does not attempt that join itself
(`docs/how-it-works.md` "Design decisions" #11). GA4 and Search Console are
named in the roster's `does` but have no field, mock row, or engine path
anywhere in this repo — a genuinely separate build, not a config flip.
`core/adapters/get_pms`/`get_sheets` exist (every repo in this family shares
the same core) but nothing in `tools/` calls them.

## Implement your own

<a id="implement-your-own"></a>

The interface is small on purpose, and your Claude Code session can do this
with you in an afternoon. Open `claude` in this folder and paste:

> Read `docs/integrations.md#implement-your-own` and
> `tools/ads_adapters.py`. I need a real Meta Ads (or Google Ads) budget
> write. Its API docs are at **<url>** and I have credentials in `.env` as
> `<VAR names>`. Copy `AdsCsv`'s shape, implement `ping`, `capabilities`,
> `set_budget` and `pause` with the platform's real API, keep the
> `@guarded_write("apply_budget_change")` decorator on both writes, and stop
> before wiring it into `get_ads()` so I can check it with `make doctor`.

### Rules that matter

- **`ping()` never raises.** It returns `HealthCheck(ok=False, ...)` with a
  hint. A broken adapter must still produce a readable doctor table.
- **Every write is decorated.** `@guarded_write("apply_budget_change")` (or
  `send_email`/`send_message` for the built-in ones) — no exceptions. The
  decorator is not optional: without it, an adapter can write while the
  agent is in shadow mode, which defeats the entire safety model.
- **Rate limits belong in the adapter.** Use `core/adapters/_http.py:RateLimiter`.
  Retry 429 and 5xx with backoff; never retry a 4xx.
- **Never log a credential.** `core/log.py` masks anything whose key looks
  like a secret, but do not rely on it.
- **Write a test.** Copy `tests/test_core_adapters_mock_csv.py`'s shape: feed
  your parser a fixture, check the dataclass that comes out, no network.

### `core/` is shared

`core/` is identical in all 28 agents in this family. If you change
something in `core/`, keep it generic — a marketing-specific tweak belongs
in `tools/`, not in the shared runtime.
