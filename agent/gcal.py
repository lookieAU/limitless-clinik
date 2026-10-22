import asyncio
import hashlib
import logging

import httpx

from shared.time import to_iso_z
from shared.types import Booking

log = logging.getLogger("agent.gcal")
TOKEN_URL = "https://oauth2.googleapis.com/token"
EVENTS_URL = "https://www.googleapis.com/calendar/v3/calendars/{calendar}/events"


def event_id(booking_id: str) -> str:
    return "clinik" + hashlib.sha1(booking_id.encode()).hexdigest()


def event_body(booking: Booking) -> dict:
    return {
        "id": event_id(booking.id),
        "summary": f"{booking.slot.doctor_name} ({booking.ref})",
        "description": f"Verified with the clinic. Booking {booking.ref}, version {booking.version}.",
        "start": {"dateTime": to_iso_z(booking.slot.start_utc), "timeZone": "UTC"},
        "end": {"dateTime": to_iso_z(booking.slot.end_utc), "timeZone": "UTC"},
        "status": "confirmed" if booking.status == "confirmed" else "cancelled",
    }


class CalendarSync:
    def __init__(self, client: httpx.AsyncClient, client_id: str, client_secret: str, refresh_token: str, calendar_id: str):
        self.client = client
        self.credentials = {"client_id": client_id, "client_secret": client_secret, "refresh_token": refresh_token}
        self.calendar_id = calendar_id
        self.tasks: set[asyncio.Task] = set()

    async def token(self) -> str:
        response = await self.client.post(TOKEN_URL, data={**self.credentials, "grant_type": "refresh_token"})
        response.raise_for_status()
        return response.json()["access_token"]

    async def push(self, booking: Booking) -> None:
        headers = {"Authorization": f"Bearer {await self.token()}"}
        base = EVENTS_URL.format(calendar=self.calendar_id)
        body = event_body(booking)
        response = await self.client.put(f"{base}/{body['id']}", json=body, headers=headers)
        if response.status_code == 404:
            response = await self.client.post(base, json=body, headers=headers)
        response.raise_for_status()

    async def safe_push(self, booking: Booking) -> None:
        try:
            await self.push(booking)
        except httpx.HTTPError as error:
            log.warning("google calendar sync failed for %s: %s", booking.ref, error)

    def schedule(self, booking: Booking) -> None:
        task = asyncio.get_running_loop().create_task(self.safe_push(booking))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def flush(self) -> None:
        if self.tasks:
            await asyncio.gather(*list(self.tasks))
