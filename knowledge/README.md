# knowledge/

This folder is what the copilot and the two narration prompts read before
they write anything. Most agents in this family read `property.md`/`faq.md`
to answer a guest directly; this agent is different — it never talks to a
guest — but the copilot still reads them for property context, and
`marketing-policy.md` is the file that actually shapes what it writes.

## What to put here

| File | What it holds |
|---|---|
| `marketing-policy.md` | **This agent's own.** Voice, claims you never make, the budget philosophy behind your thresholds, review-quote and seasonal notes. See `knowledge/marketing-policy.example.md`. |
| `property.md` | The facts — rooms, times, prices, policies. Read by the copilot for grounding, not quoted to a guest directly. |
| `faq.md` | Generic scaffold template. Read by the copilot the same way. |
| `signature.md` | Generic scaffold template. Not read by this agent — it sends no guest email. |

Copy the files that matter here:

```bash
cp knowledge/marketing-policy.example.md knowledge/marketing-policy.md
cp knowledge/property.example.md         knowledge/property.md
cp knowledge/faq.example.md              knowledge/faq.md
```

`knowledge/*.md` is gitignored (the `.example.md` files are not), because
your property notes are yours.

## How to write it

**Write `marketing-policy.md` the way you would brief a new marketing
hire.** Short sentences, the real reasoning, no filler. Say why, not just
what — why brand-term search stays capped, why one offer per creative,
what "not this quarter" usually means when you reject a suggestion.

**Be specific about numbers and thresholds.** `config/agent.yaml` has the
budget numbers; this file is for the reasoning that does not fit in a YAML
comment.

**Say what you never claim.** A list of banned phrases and unverifiable
superlatives does more work than a paragraph of good intentions.

**Keep it dated.** Note when you last reviewed it — a voice guide with no
date on it goes stale silently.

## Keeping it current

Whenever you reject a suggestion or edit a budget change, ask whether the
reason belongs in `marketing-policy.md`. If it does, the next run's note is
grounded in it, and the copilot stops suggesting the thing you just turned
down.

You can also ask your Claude Code session to do it:

> Read knowledge/marketing-policy.md and the last ten rejected items in the
> review queue. If any of my rejection reasons are not reflected in the
> policy file, tell me which line to add.
