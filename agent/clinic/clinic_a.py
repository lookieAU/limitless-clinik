from agent.clinic.adapter import ClinicAdapter
from shared.types import Booking, ClinicEventType


class ClinicAAdapter(ClinicAdapter):
    event_types = {
        "booking.created": ClinicEventType.CREATED,
        "booking.rescheduled": ClinicEventType.RESCHEDULED,
        "booking.cancelled": ClinicEventType.CANCELLED,
    }

    async def reschedule(self, booking: Booking, slot_id: str, key: str) -> list[Booking]:
        raw = await self.call(
            "PATCH",
            f"/bookings/{booking.id}",
            headers={"Idempotency-Key": key, "If-Match": str(booking.version)},
            json={"slot_id": slot_id},
        )
        return [self.normalize_booking(raw)]
