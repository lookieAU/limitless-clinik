from dataclasses import dataclass, field
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class ClinicConfig:
    id: str
    name: str
    tz: str
    ref_prefix: str
    delivery: str
    reschedule_in_place: bool
    cancel_cutoff_hours: int
    status_names: dict[str, str]
    event_names: dict[str, str]
    doctors: dict[str, str] = field(default_factory=dict)

    @property
    def zone(self) -> ZoneInfo:
        return ZoneInfo(self.tz)

    def raw_status(self, status: str, cancelled_by: str | None) -> str:
        if status == "cancelled":
            return self.status_names[f"cancelled_by_{cancelled_by or 'customer'}"]
        return self.status_names[status]

    def policy(self) -> dict:
        return {
            "delivery": self.delivery,
            "reschedule_in_place": self.reschedule_in_place,
            "cancel_cutoff_hours": self.cancel_cutoff_hours,
        }


CLINICS = {
    "clinic_a": ClinicConfig(
        id="clinic_a",
        name="Indiranagar Family Clinic",
        tz="Asia/Kolkata",
        ref_prefix="CA",
        delivery="webhook",
        reschedule_in_place=True,
        cancel_cutoff_hours=0,
        status_names={
            "confirmed": "confirmed",
            "cancelled_by_customer": "cancelled",
            "cancelled_by_clinic": "cancelled",
        },
        event_names={
            "created": "booking.created",
            "rescheduled": "booking.rescheduled",
            "cancelled": "booking.cancelled",
        },
        doctors={"dr_a": "Dr Arjun Mehta", "dr_b": "Dr Bela Nair", "dr_c": "Dr Chetan Rao"},
    ),
    "clinic_b": ClinicConfig(
        id="clinic_b",
        name="Marina Health Centre",
        tz="Asia/Dubai",
        ref_prefix="CB",
        delivery="polling",
        reschedule_in_place=False,
        cancel_cutoff_hours=24,
        status_names={
            "confirmed": "confirmed",
            "cancelled_by_customer": "voided",
            "cancelled_by_clinic": "cancelled_by_clinic",
        },
        event_names={
            "created": "appointment.created",
            "rescheduled": "appointment.moved",
            "cancelled": "appointment.voided",
        },
        doctors={"dr_f": "Dr Farah Khan", "dr_o": "Dr Omar Haddad"},
    ),
}

CUSTOMERS = ("c_asha", "c_ravi", "c_mei", "c_walkin")
