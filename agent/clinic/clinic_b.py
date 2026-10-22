from agent.clinic.adapter import ClinicAdapter
from shared.types import Booking, ClinicEvent, ClinicEventType


class ClinicBAdapter(ClinicAdapter):
    event_types = {
        "appointment.created": ClinicEventType.CREATED,
        "appointment.moved": ClinicEventType.RESCHEDULED,
        "appointment.voided": ClinicEventType.CANCELLED,
    }

    async def reschedule(self, booking: Booking, slot_id: str, key: str) -> list[Booking]:
        rebooked = await self.book(booking.customer_id, slot_id, f"{key}:book")
        cancelled = await self.cancel(booking, f"{key}:cancel")
        return rebooked + cancelled

    async def reconcile_key(self, action: str, key: str) -> list[Booking]:
        return await self.find_by_key(f"{key}:book" if action == "reschedule" else key)

    async def poll_events(self, since: int) -> tuple[list[ClinicEvent], int]:
        raw = await self.call("GET", "/events", params={"since": since})
        events = [event for item in raw["events"] if (event := self.normalize_event(item))]
        return events, raw["cursor"]
