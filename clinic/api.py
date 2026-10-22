import asyncio
import json
from collections.abc import Callable

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from clinic.clinics import CLINICS, ClinicConfig
from clinic.context import ClinicContext
from clinic.faults import take_fault
from clinic.repo import (
    ClinicError,
    booking_for_key,
    booking_json,
    booking_row,
    bookings_for_customer,
    doctors,
    events_since,
    list_slots,
)
from clinic.service import cancel_booking, create_booking, move_booking, request_hash, run_idempotent
from shared.time import parse_utc, to_iso_z


class BookRequest(BaseModel):
    customer_id: str
    slot_id: str


class MoveRequest(BaseModel):
    slot_id: str


def context(request: Request) -> ClinicContext:
    return request.app.state.ctx


def clinic_config(clinic_id: str, request: Request, x_api_key: str | None = Header(default=None)) -> ClinicConfig:
    if x_api_key != context(request).settings.api_key:
        raise ClinicError(401, "unauthorized")
    if clinic_id not in CLINICS:
        raise ClinicError(404, "clinic_not_found")
    return CLINICS[clinic_id]


def require_key(key: str | None) -> str:
    if not key:
        raise ClinicError(400, "idempotency_key_required")
    return key


async def guarded_write(
    ctx: ClinicContext, endpoint: str, key: str, req_hash: str, action: Callable[[], tuple[int, dict]]
) -> JSONResponse:
    mode = take_fault(ctx.conn, endpoint)
    if mode == "slow":
        await asyncio.sleep(ctx.settings.slow_seconds)
    if mode == "timeout_before_commit":
        await asyncio.sleep(ctx.settings.hang_seconds)
        raise ClinicError(504, "upstream_timeout")
    status, body = run_idempotent(ctx.conn, key, req_hash, ctx.clock.now(), action)
    if mode == "timeout_after_commit":
        await asyncio.sleep(ctx.settings.hang_seconds)
    return JSONResponse(body, status_code=status)


router = APIRouter(prefix="/clinics/{clinic_id}")


@router.get("/doctors")
async def get_doctors(request: Request, clinic: ClinicConfig = Depends(clinic_config)) -> dict:
    return {"doctors": doctors(context(request).conn, clinic.id), "tz": clinic.tz}


@router.get("/slots")
async def get_slots(
    request: Request,
    start: str = Query(alias="from"),
    end: str = Query(alias="to"),
    doctor_id: str | None = None,
    available: bool = True,
    clinic: ClinicConfig = Depends(clinic_config),
) -> dict:
    window = to_iso_z(parse_utc(start)), to_iso_z(parse_utc(end))
    return {"slots": list_slots(context(request).conn, clinic.id, doctor_id, *window, available)}


@router.get("/bookings")
async def find_bookings(
    request: Request,
    customer_id: str | None = None,
    idempotency_key: str | None = None,
    clinic: ClinicConfig = Depends(clinic_config),
) -> dict:
    conn = context(request).conn
    if idempotency_key:
        return {"bookings": booking_for_key(conn, clinic.id, idempotency_key)}
    if customer_id:
        return {"bookings": bookings_for_customer(conn, clinic.id, customer_id)}
    raise ClinicError(400, "filter_required")


@router.get("/bookings/{booking_id}")
async def get_booking(booking_id: str, request: Request, clinic: ClinicConfig = Depends(clinic_config)) -> dict:
    conn = context(request).conn
    return booking_json(conn, booking_row(conn, clinic.id, booking_id))


@router.post("/bookings")
async def post_booking(
    body: BookRequest,
    request: Request,
    idempotency_key: str | None = Header(default=None),
    clinic: ClinicConfig = Depends(clinic_config),
) -> JSONResponse:
    ctx = context(request)
    key = require_key(idempotency_key)
    digest = request_hash("POST", request.url.path, body.model_dump())
    return await guarded_write(
        ctx, "book", key, digest, lambda: (201, create_booking(ctx.conn, clinic, body.customer_id, body.slot_id, ctx.clock.now()))
    )


@router.patch("/bookings/{booking_id}")
async def patch_booking(
    booking_id: str,
    body: MoveRequest,
    request: Request,
    idempotency_key: str | None = Header(default=None),
    if_match: str | None = Header(default=None),
    clinic: ClinicConfig = Depends(clinic_config),
) -> JSONResponse:
    if not clinic.reschedule_in_place:
        raise ClinicError(405, "reschedule_not_supported", "cancel and rebook instead")
    if not if_match:
        raise ClinicError(428, "if_match_required")
    ctx = context(request)
    key = require_key(idempotency_key)
    version = int(if_match.strip('"'))
    digest = request_hash("PATCH", request.url.path, {**body.model_dump(), "version": version})
    now = ctx.clock.now()
    return await guarded_write(
        ctx,
        "reschedule",
        key,
        digest,
        lambda: (200, move_booking(ctx.conn, clinic, booking_id, body.slot_id, version, now, "customer")[0]),
    )


@router.delete("/bookings/{booking_id}")
async def delete_booking(
    booking_id: str,
    request: Request,
    idempotency_key: str | None = Header(default=None),
    clinic: ClinicConfig = Depends(clinic_config),
) -> JSONResponse:
    ctx = context(request)
    key = require_key(idempotency_key)
    digest = request_hash("DELETE", request.url.path, {})
    now = ctx.clock.now()
    return await guarded_write(
        ctx, "cancel", key, digest, lambda: (200, cancel_booking(ctx.conn, clinic, booking_id, now, "customer")[0])
    )


@router.get("/events")
async def get_events(request: Request, since: int = 0, clinic: ClinicConfig = Depends(clinic_config)) -> dict:
    rows, cursor = events_since(context(request).conn, clinic.id, since)
    return {"events": [json.loads(row["payload_json"]) for row in rows], "cursor": cursor}
