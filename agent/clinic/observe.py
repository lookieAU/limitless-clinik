from datetime import datetime

from agent.notices import create_notice
from agent.repo import claims, users, verified
from agent.repo.audit import log_event
from shared.time import to_iso_z
from shared.types import Booking, BookingStatus


def classify(previous: dict | None, booking: Booking) -> str | None:
    if previous is None or previous["status"] != BookingStatus.CONFIRMED:
        return None
    if booking.status == BookingStatus.CANCELLED:
        return "booking_cancelled"
    if previous["slot"]["id"] != booking.slot.id:
        return "booking_rescheduled"
    return None


def upsert(ctx, booking: Booking, source: str, session_id: str | None, now: datetime) -> None:
    ctx.conn.execute(
        "INSERT INTO verified_state (booking_id, clinic_id, customer_id, ref, status, slot_json, version, source, "
        "observed_utc, fetched_in_session) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(booking_id) DO UPDATE SET status = excluded.status, slot_json = excluded.slot_json, "
        "version = excluded.version, source = excluded.source, observed_utc = excluded.observed_utc, "
        "fetched_in_session = excluded.fetched_in_session, ref = excluded.ref",
        (
            booking.id,
            booking.clinic_id,
            booking.customer_id,
            booking.ref,
            booking.status.value,
            booking.slot.model_dump_json(),
            booking.version,
            source,
            to_iso_z(now),
            session_id if source == "api" else None,
        ),
    )


def observe(
    ctx,
    booking: Booking,
    source: str,
    origin: str,
    session_id: str | None = None,
    event_id: str | None = None,
    require_newer: bool = False,
    occurred_utc: datetime | None = None,
) -> str | None:
    now = ctx.clock.now()
    previous = verified.get(ctx.conn, booking.id)
    if previous and (booking.version < previous["version"] or (require_newer and booking.version <= previous["version"])):
        return None
    upsert(ctx, booking, source, session_id, now)
    user = users.by_customer(ctx.conn, booking.customer_id)
    transition = classify(previous, booking) if origin == "clinic" else None
    if user and transition:
        params = {
            "ref": booking.ref,
            "clinic_id": booking.clinic_id,
            "doctor": booking.slot.doctor_name,
            "start_utc": to_iso_z(booking.slot.start_utc),
            "source": source,
            "at": to_iso_z(occurred_utc or now),
        }
        create_notice(ctx.conn, user["id"], booking.id, transition, params, now, event_id)
        overridden = claims.override_for_booking(ctx.conn, booking.id, event_id or f"{source}:{booking.version}")
        log_event(
            ctx.conn,
            now,
            "clinic_change",
            {"transition": transition, "ref": booking.ref, "source": source, "overridden_claims": overridden},
            user_id=user["id"],
        )
    if user:
        ctx.bus.publish(user["id"], "panels")
        if ctx.calendar_sync:
            ctx.calendar_sync.schedule(booking)
    return transition
