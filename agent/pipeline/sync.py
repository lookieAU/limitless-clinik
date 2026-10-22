import json

import httpx

from agent import outbox
from agent.clinic.adapter import ClinicAdapter, ClinicFailure, ClinicTimeout
from agent.clinic.observe import observe
from agent.repo import sessions
from agent.repo.audit import log_event
from shared.time import parse_utc

CLINIC_ERRORS = (ClinicTimeout, ClinicFailure, httpx.HTTPError)


def needs_sync(ctx, session: dict) -> bool:
    if not session.get("synced_utc"):
        return True
    return (ctx.clock.now() - parse_utc(session["synced_utc"])).total_seconds() > ctx.settings.sync_gap_s


def apply_event(ctx, event, source: str) -> str | None:
    inserted = ctx.conn.execute(
        "INSERT OR IGNORE INTO processed_events (event_id, received_utc) VALUES (?, ?)",
        (event.event_id, ctx.clock.now().isoformat()),
    ).rowcount
    if not inserted:
        return "duplicate"
    transition = observe(
        ctx, event.booking, source, "clinic", event_id=event.event_id, require_newer=True, occurred_utc=event.occurred_utc
    )
    return transition or "applied"


async def poll_clinic(ctx, adapter: ClinicAdapter) -> int:
    row = ctx.conn.execute("SELECT last_seq FROM poll_cursors WHERE clinic_id = ?", (adapter.id,)).fetchone()
    events, cursor = await adapter.poll_events(row["last_seq"] if row else 0)
    for event in events:
        apply_event(ctx, event, "poll")
    ctx.conn.execute(
        "INSERT INTO poll_cursors (clinic_id, last_seq) VALUES (?, ?) ON CONFLICT(clinic_id) DO UPDATE SET last_seq = excluded.last_seq",
        (adapter.id, cursor),
    )
    return len(events)


async def poll_all(ctx) -> None:
    for adapter in ctx.registry.enabled():
        if adapter.policy.cancellation.delivery == "polling":
            try:
                await poll_clinic(ctx, adapter)
            except CLINIC_ERRORS as error:
                log_event(ctx.conn, ctx.clock.now(), "poll_failed", {"clinic": adapter.id, "error": str(error)})


async def reconcile_unknown(ctx, user: dict, session_id: str) -> None:
    for row in outbox.unknown_for_user(ctx.conn, user["id"]):
        adapter = ctx.registry.get(json.loads(row["payload_json"])["clinic_id"])
        try:
            found = await adapter.reconcile_key(row["action"], row["idempotency_key"])
        except CLINIC_ERRORS:
            continue
        for booking in found:
            observe(ctx, booking, "api", "agent", session_id)
        state = "succeeded" if found else "failed"
        outbox.mark(ctx.conn, row["id"], state, ctx.clock.now(), {"bookings": [b.model_dump(mode="json") for b in found]})
        log_event(ctx.conn, ctx.clock.now(), "outbox_reconciled", {"key": row["idempotency_key"][:12], "state": state}, user["id"], session_id)


async def sync_customer(ctx, user: dict, session_id: str) -> bool:
    ok = True
    await poll_all(ctx)
    for adapter in ctx.registry.enabled():
        try:
            for booking in await adapter.bookings_for_customer(user["customer_id"]):
                observe(ctx, booking, "api", "clinic", session_id)
        except CLINIC_ERRORS as error:
            ok = False
            log_event(ctx.conn, ctx.clock.now(), "sync_failed", {"clinic": adapter.id, "error": str(error)}, user["id"], session_id)
    await reconcile_unknown(ctx, user, session_id)
    if ok:
        sessions.mark_synced(ctx.conn, session_id, ctx.clock.now())
    log_event(ctx.conn, ctx.clock.now(), "session_sync", {"ok": ok}, user["id"], session_id)
    return ok
