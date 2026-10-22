from enum import StrEnum

from pydantic import AwareDatetime, BaseModel


class BookingStatus(StrEnum):
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class ClinicEventType(StrEnum):
    CREATED = "booking.created"
    RESCHEDULED = "booking.rescheduled"
    CANCELLED = "booking.cancelled"


class Slot(BaseModel):
    id: str
    clinic_id: str
    doctor_id: str
    doctor_name: str
    start_utc: AwareDatetime
    end_utc: AwareDatetime
    available: bool = True


class Booking(BaseModel):
    id: str
    ref: str
    clinic_id: str
    customer_id: str
    status: BookingStatus
    slot: Slot
    version: int


class ClinicEvent(BaseModel):
    event_id: str
    type: ClinicEventType
    occurred_utc: AwareDatetime
    booking: Booking
