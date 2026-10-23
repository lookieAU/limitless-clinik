# Clinik by Limitless — a booking agent that knows what is true

A clinic booking agent (text, plus an optional voice transport) that never claims something the clinic hasn't
confirmed. The trust rules live in code, not in the prompt, so every scenario passes with a scripted fake LLM.

## Run

```bash
cp .env.example .env     # add OPENROUTER_API_KEY and the LIVEKIT_* values
docker compose up --build
```

One command starts the clinic (:8001), the agent with its chat UI (:8000), the voice worker and the scripted
replay (:8002).

- Open <http://localhost:8000>, pick a customer, enter the code shown. Use the **Chat / Voice** switch at the top;
  switching always starts a fresh conversation. Voice runs in the browser (allow the microphone).
- **Demo controls** (top bar): clinic cancels a booking (with or without losing the webhook), make the next booking
  time out, jump a day, run the nightly summary (or a broken one that drops "not"), enable the second clinic, reset.
- **Replay**: <http://localhost:8002/replay> steps through "the appointment that changed four times".
- Tests: `uv run pytest` (scripted model, fixed clock) · `uv run pytest -m live` (real model).
- Model: Claude Haiku 5.5 via OpenRouter by default (`OPENROUTER_MODEL`), or the Anthropic API (`LLM_PROVIDER=anthropic`).

## State model

Claims (what the customer said) and verified state (what the clinic returned) live in separate tables with their
own timestamps and sources. Events are an append-only audit log. Memory summaries are built from claims and loaded
back only as claims. A clinic change overrides earlier claims and memory. Details and diagram: [docs/state-model.md](docs/state-model.md).

## Where the guarantees live

| Guarantee | Code | Proof |
|---|---|---|
| No "confirmed" unless the clinic said so this conversation, ≤ 2 min ago | `agent/pipeline/verify_reply.py`, `status.py`, templates | S5, S5b (an LLM that lies is blocked) |
| No booking without explicit choice or a "yes" to an offer; 1 write per turn; no bulk tools | `agent/pipeline/policy_gate.py`, `consent.py` | S2, S8 |
| Contradictions → one question, writes locked | `agent/pipeline/conflicts.py`, `clarify.py` | S3, Hinglish test |
| Webhook overrides claims and memory; told first on next contact | `agent/clinic/observe.py`, `pipeline/sync.py` | S4 |
| Negation survives summarisation (en + hi) | `agent/memory/validate_summary.py`, `negation_lexicon.py` | S6 (`tests/scenarios/test_s06_negation_summary.py`) |
| Idempotent writes, timeouts reconciled before any retry | `agent/outbox.py`, `tools/writes.py`, clinic idempotency table | S7, S9a, S9b |
| A customer can only touch their own bookings | `policy_gate.authorize` | `tests/additions/test_authz.py` |
| A second clinic is an adapter + a policy file | `agent/clinic/clinic_b.py`, `policies/clinic_b.json` | `tests/additions/test_clinic_b.py` |

Negation demo: run `test_lossy_summarizer_is_rejected`, or click "Run with lossy summarizer" in `/admin` to see
`summary_rejected` in the event log while the previous validated memory stays in use.

## What I cut

- **Payments**: schema migrated and the saga designed ([docs/payments.md](docs/payments.md)); five named tests are skipped. No payment endpoints or tools.
- **OAuth/SSO**: login is a seeded customer plus a mock one-time code and a signed cookie; authorisation is real.
- **Production webhook infrastructure**: in-process retries only, no queue or dead-letter store. Session-start sync is the safety net.
- **More than two languages**, group bookings.
- **Voice and Google Calendar** are built but only tested through their bridges/mocks; they need LiveKit and Google credentials to run for real.

## What's next

Turn on payments behind the same gate/outbox/verifier, per-customer clinic accounts instead of shared ids, a durable
webhook queue, and evals on extraction quality for Hinglish.
