from datetime import timedelta

from fastapi import APIRouter, Request
from pydantic import BaseModel

from clinic.api import context
from clinic.clinics import CLINICS
from clinic.faults import all_faults, set_fault
from clinic.repo import ClinicError, booking_row
from clinic.seed import reset
from clinic.service import cancel_booking, cancel_slot, fill_slot, move_booking
from shared.sqlite import many, transaction


class FaultRequest(BaseModel):
    endpoint: str
    mode: str


class StaffEdit(BaseModel):
    version: int
    slot_id: str


class ClockAdvance(BaseModel):
    seconds: float


router = APIRouter(prefix="/admin")


@router.post("/slots/{slot_id}/cancel")
async def admin_cancel_slot(slot_id: str, request: Request, deliver: bool = True) -> dict:
    ctx = context(request)
    events = cancel_slot(ctx.conn, slot_id, ctx.clock.now())
    delivered = await ctx.webhooks.deliver_all(events) if deliver else []
    return {"cancelled": [event["booking"] for event in events], "delivered": delivered}


@router.post("/slots/{slot_id}/fill")
async def admin_fill_slot(slot_id: str, request: Request) -> dict:
    fill_slot(context(request).conn, slot_id)
    return {"filled": slot_id}


@router.post("/bookings/{booking_id}/cancel")
async def admin_cancel_booking(booking_id: str, request: Request, deliver: bool = True) -> dict:
    ctx = context(request)
    row = ctx.conn.execute("SELECT clinic_id FROM bookings WHERE id = ?", (booking_id,)).fetchone()
    if row is None:
        raise ClinicError(404, "booking_not_found")
    with transaction(ctx.conn):
        booking, event = cancel_booking(ctx.conn, CLINICS[row["clinic_id"]], booking_id, ctx.clock.now(), "clinic")
    delivered = await ctx.webhooks.deliver_all([event]) if deliver and event else []
    return {"booking": booking, "delivered": delivered}


@router.post("/bookings/{booking_id}/staff_edit")
async def admin_staff_edit(booking_id: str, body: StaffEdit, request: Request, deliver: bool = True) -> dict:
    ctx = context(request)
    row = ctx.conn.execute("SELECT clinic_id FROM bookings WHERE id = ?", (booking_id,)).fetchone()
    if row is None:
        raise ClinicError(404, "booking_not_found")
    clinic = CLINICS[row["clinic_id"]]
    with transaction(ctx.conn):
        booking, event = move_booking(ctx.conn, clinic, booking_id, body.slot_id, body.version, ctx.clock.now(), "clinic")
    delivered = await ctx.webhooks.deliver_all([event]) if deliver else []
    return {"booking": booking, "delivered": delivered}


@router.post("/faults")
async def admin_set_fault(body: FaultRequest, request: Request) -> dict:
    try:
        set_fault(context(request).conn, body.endpoint, body.mode)
    except ValueError as error:
        raise ClinicError(400, "unknown_fault", str(error)) from error
    return all_faults(context(request).conn)


@router.get("/faults")
async def admin_get_faults(request: Request) -> dict:
    return all_faults(context(request).conn)


@router.post("/clock")
async def admin_clock(body: ClockAdvance, request: Request) -> dict:
    ctx = context(request)
    if not hasattr(ctx.clock, "advance"):
        raise ClinicError(409, "clock_not_adjustable")
    ctx.clock.advance(timedelta(seconds=body.seconds))
    return {"now": ctx.clock.now().isoformat()}


@router.post("/reset")
async def admin_reset(request: Request) -> dict:
    ctx = context(request)
    return reset(ctx.conn, ctx.clock)


@router.get("/bookings")
async def admin_bookings(request: Request) -> dict:
    conn = context(request).conn
    rows = many(conn, "SELECT id, ref, clinic_id, customer_id, slot_id, status, version FROM bookings ORDER BY id")
    return {"bookings": rows}


@router.get("/bookings/{booking_id}")
async def admin_booking(booking_id: str, request: Request) -> dict:
    ctx = context(request)
    row = ctx.conn.execute("SELECT clinic_id FROM bookings WHERE id = ?", (booking_id,)).fetchone()
    if row is None:
        raise ClinicError(404, "booking_not_found")
    return booking_row(ctx.conn, row["clinic_id"], booking_id)
