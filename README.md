# Clinik by Limitless — a booking agent that knows what is true

A clinic booking agent (text, plus an optional voice transport) that never claims something the clinic hasn't
confirmed. The trust rules live in code, not in the prompt, so every scenario passes with a scripted fake LLM.

## Run

```bash
cp .env.example .env          # add ANTHROPIC_API_KEY for live chat; everything else has demo defaults
docker compose up --build     # clinic :8001, agent UI :8000, scripted replay :8002
```

- Chat UI: <http://localhost:8000> (pick a seeded customer, use the code shown). Admin console at `/admin`:
  clinic-side cancel (with or without losing the webhook), fault injection, clock jump, nightly summary
  (and the lossy version), enable Clinic B, reset.
- Replay: <http://localhost:8002/replay>, or in the terminal `uv run python -m demo.replay` (`--live` uses the real LLM).
- Tests: `uv run pytest` (scripted LLM, fixed clock) · `uv run pytest -m live` (same guarantees against Claude).
- Voice (optional): fill the `LIVEKIT_*` values, then `docker compose --profile voice up`.
- Nightly summary by hand: `docker compose exec agent python -m agent.memory.summarize --user c_asha --date 2026-11-02`.

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
