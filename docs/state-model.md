# State model

Clinik keeps four kinds of state and never merges them.

```
 customer message ──▶ extract (LLM) ──▶ CLAIMS            what the customer said: subject, value, polarity,
                                         (claims table)     raw text, language, status (active / clarified /
                                                            superseded / overridden), timestamp, source
 clinic API / webhook / poll ──▶ adapter ──▶ VERIFIED      what the clinic returned: status, slot, version,
                                         (verified_state)   source (api / webhook / poll), observed_utc,
                                                            fetched_in_session
 everything that happened ──▶ EVENTS (append-only audit: tool calls, gate refusals, injection flags,
                                       reply blocks, webhooks, summary rejections)
 nightly ──▶ MEMORY (memory_summaries: structured JSON built from claims + prose written by the LLM,
                     kept only if the validator passes; loaded later as claims, never as verified state)
```

## Who may write what

| Store | Only writer |
|---|---|
| `claims` | `agent/pipeline/extract_claims.py` (after grounding checks: the span must be in the message; a day claim must name that day) |
| `verified_state` | `agent/clinic/observe.py`, called with clinic API responses, signed webhooks and polled events |
| `outbox` | `agent/tools/writes.py`, before any clinic HTTP call |
| `memory_summaries` | `agent/memory/summarize.py`, with `validated` set by `validate_summary.py` |

The agent learns clinic state only over HTTP (a boundary test forbids importing the clinic package).

## Freshness rule

A booking-status sentence ("confirmed", "cancelled", "कन्फर्म", "रद्द") may appear only in a template line
rendered from a `verified_state` row that is at most `FRESHNESS_TTL_S` (120 s) old **and** came from an API read in
this session or from a webhook/poll. Stale rows are re-fetched before replying. LLM prose may not contain status
vocabulary at all: if it does, the reply is blocked, the clinic is re-checked, the prose is regenerated once, and
then replaced by "checking with the clinic…" if it still fails.

## Overrides

A clinic change (webhook, poll, or a difference found at session-start sync) marks the positive claims tied to that
booking `overridden` and queues a notice that is delivered first on next contact. Negative constraints ("NOT this
week") survive: the clinic cancelling a slot doesn't change what the customer ruled out. When memory loads, summary
constraints whose claims were all overridden, and clinic snapshots older than current verified state, are dropped.

## Time

Stored timestamps are UTC with `Z`. "Thursday 3pm" is resolved in the clinic's timezone. Replies show clinic time,
plus customer time when they differ. A lint test forbids wall-clock reads outside `shared/clock.py`.
