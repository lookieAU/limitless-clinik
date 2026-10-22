# Payments — designed, schema migrated, not wired

Payments are cut from this build. The tables exist (`agent/migrations/002_payments.sql`) and the tests are named
and skipped (`tests/payments/test_payments.py`). There are **no payment endpoints and no payment tools**.

## Why it fits the existing design

A payment provider is a second system of record. Everything that keeps booking status honest applies unchanged:

| Booking today | Payments |
|---|---|
| `claims` vs `verified_state` | "I already paid" is a claim (`claims.kind = 'payment'`, reserved). Only provider responses and provider webhooks write `payment_intents.status` / `observed_utc`. |
| Policy gate | Capture is a write: it needs a verified `confirmed` booking for the same customer, observed within the freshness TTL. |
| Outbox + idempotency key | One outbox row and one provider idempotency key per step (`authorize`, `capture`, `void`, `refund`), derived from `(user, step, booking, intent_id)`. |
| Reply verifier | "paid", "charged", "refunded" join the status vocabulary and need a fresh verified payment row, exactly like "confirmed". |
| Webhooks | Provider webhooks are HMAC-verified, deduped on event id and applied only if newer, then create a `pending_notice`. |

## State machine

```
requires_authorization ──authorize──▶ authorized ──capture──▶ captured ──refund──▶ refunded
          │                               │
          └──────────fail────────▶ failed └──void──▶ voided
```

## Saga: authorize → book → capture

1. **Authorize** the amount (hold, no money moves). Outbox row `pending → succeeded`, intent `authorized`.
2. **Book** at the clinic with the booking idempotency key.
3. If the clinic returns `confirmed`: **capture**. If the booking fails or is refused: **void** the authorization.
4. On a timeout at any step: mark the outbox row `unknown`, reconcile by idempotency key with the provider
   (or the clinic), then retry with the same key only if nothing was recorded — the same rule as Scenario 9.
5. On a clinic **cancellation webhook**: refund per the clinic's policy (`refund_policy` would join the clinic policy
   JSON next to `customer_cancel_cutoff_hours`), and tell the customer the refund status only once the provider
   confirms it.

## What I would build next

Provider adapter (`PaymentAdapter` protocol mirroring `ClinicAdapter`), the four tools behind the gate, provider
webhook receiver, and turning the five skipped tests on.
