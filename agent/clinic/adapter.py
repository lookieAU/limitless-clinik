import asyncio
from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo

import httpx
from pydantic import BaseModel

from shared.time import to_iso_z
from shared.types import Booking, BookingStatus, ClinicEvent, ClinicEventType, Slot


class CancellationPolicy(BaseModel):
    delivery: Literal["webhook", "polling"]
    status_values: list[str]


class ClinicPolicy(BaseModel):
    id: str
    name: str
    tz: str
    cancellation: CancellationPolicy
    customer_cancel_cutoff_hours: int
    reschedule_mode: Literal["in_place", "cancel_and_rebook"]
    max_active_bookings_per_customer: int

    @property
    def zone(self) -> ZoneInfo:
        return ZoneInfo(self.tz)


class ClinicTimeout(Exception):
    pass


class ClinicFailure(Exception):
    def __init__(self, status: int, code: str, detail: str = ""):
        super().__init__(f"{status} {code}")
        self.status = status
        self.code = code
        self.detail = detail


class ClinicAdapter:
    event_types: dict[str, ClinicEventType] = {}

    def __init__(self, policy: ClinicPolicy, client: httpx.AsyncClient, api_key: str, timeout_s: float):
        self.policy = policy
        self.client = client
        self.api_key = api_key
        self.timeout_s = timeout_s

    @property
    def id(self) -> str:
        return self.policy.id

    @property
    def tz(self) -> ZoneInfo:
        return self.policy.zone

    async def call(self, method: str, path: str, headers: dict | None = None, **kwargs) -> dict:
        merged = {"X-Api-Key": self.api_key, **(headers or {})}
        try:
            async with asyncio.timeout(self.timeout_s):
                response = await self.client.request(method, f"/clinics/{self.id}{path}", headers=merged, **kwargs)
        except (TimeoutError, httpx.TimeoutException) as error:
            raise ClinicTimeout(f"{self.id} {method} {path}") from error
        if response.status_code >= 400:
            body = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
            raise ClinicFailure(response.status_code, body.get("error", "clinic_error"), body.get("detail", ""))
        return response.json()

    def normalize_status(self, raw: str) -> BookingStatus:
        if raw in self.policy.cancellation.status_values:
            return BookingStatus.CANCELLED
        if raw == "confirmed":
            return BookingStatus.CONFIRMED
        raise ClinicFailure(502, "unknown_status", raw)

    def normalize_booking(self, raw: dict) -> Booking:
        return Booking(
            id=raw["booking_id"],
            ref=raw["ref"],
            clinic_id=self.id,
            customer_id=raw["customer_id"],
            status=self.normalize_status(raw["status"]),
            slot=Slot(**raw["slot"]),
            version=raw["version"],
        )

    def normalize_event(self, raw: dict) -> ClinicEvent | None:
        event_type = self.event_types.get(raw.get("type", ""))
        if event_type is None:
            return None
        return ClinicEvent(
            event_id=raw["event_id"],
            type=event_type,
            occurred_utc=raw["occurred_utc"],
            booking=self.normalize_booking(raw["booking"]),
        )

    async def doctors(self) -> list[dict]:
        return (await self.call("GET", "/doctors"))["doctors"]

    async def list_slots(self, start: datetime, end: datetime, doctor_id: str | None = None) -> list[Slot]:
        params = {"from": to_iso_z(start), "to": to_iso_z(end)}
        if doctor_id:
            params["doctor_id"] = doctor_id
        return [Slot(**slot) for slot in (await self.call("GET", "/slots", params=params))["slots"]]

    async def get_booking(self, booking_id: str) -> Booking:
        return self.normalize_booking(await self.call("GET", f"/bookings/{booking_id}"))

    async def bookings_for_customer(self, customer_id: str) -> list[Booking]:
        raw = await self.call("GET", "/bookings", params={"customer_id": customer_id})
        return [self.normalize_booking(item) for item in raw["bookings"]]

    async def find_by_key(self, key: str) -> list[Booking]:
        raw = await self.call("GET", "/bookings", params={"idempotency_key": key})
        return [self.normalize_booking(item) for item in raw["bookings"]]

    async def book(self, customer_id: str, slot_id: str, key: str) -> list[Booking]:
        raw = await self.call(
            "POST", "/bookings", headers={"Idempotency-Key": key}, json={"customer_id": customer_id, "slot_id": slot_id}
        )
        return [self.normalize_booking(raw)]

    async def cancel(self, booking: Booking, key: str) -> list[Booking]:
        raw = await self.call("DELETE", f"/bookings/{booking.id}", headers={"Idempotency-Key": key})
        return [self.normalize_booking(raw)]

    async def reschedule(self, booking: Booking, slot_id: str, key: str) -> list[Booking]:
        raise NotImplementedError

    async def reconcile_key(self, action: str, key: str) -> list[Booking]:
        return await self.find_by_key(key)

    async def poll_events(self, since: int) -> tuple[list[ClinicEvent], int]:
        return [], since
