import json
import logging
import sqlite3
from datetime import date, datetime, time, timedelta

from clinic.clinics import CLINICS, CUSTOMERS, ClinicConfig
from clinic.repo import ClinicError
from clinic.service import create_booking, move_booking
from shared.clock import Clock
from shared.sqlite import one, transaction
from shared.time import local_to_utc, to_iso_z, to_local, week_start

log = logging.getLogger("clinic.seed")

TABLES = ("events", "idempotency_keys", "bookings", "slots", "doctors", "customers", "clinics", "faults")
SLOT_MINUTES = 30
DAY_START = time(9, 0)
DAY_END = time(17, 0)
WEEKS = 2


def slot_id(doctor_id: str, day: date, start: time) -> str:
    return f"{doctor_id}_{day:%Y%m%d}_{start:%H%M}"


def first_monday(clinic: ClinicConfig, now: datetime) -> date:
    return week_start(to_local(now, clinic.zone).date())


def slot_rows(clinic: ClinicConfig, now: datetime):
    monday = first_monday(clinic, now)
    for offset in range(WEEKS * 7):
        day = monday + timedelta(days=offset)
        if day.weekday() >= 5:
            continue
        for doctor_id in clinic.doctors:
            cursor = datetime.combine(day, DAY_START)
            while cursor.time() < DAY_END:
                start = local_to_utc(day, cursor.time(), clinic.zone)
                yield (
                    slot_id(doctor_id, day, cursor.time()),
                    doctor_id,
                    to_iso_z(start),
                    to_iso_z(start + timedelta(minutes=SLOT_MINUTES)),
                )
                cursor += timedelta(minutes=SLOT_MINUTES)


def insert_reference_data(conn: sqlite3.Connection, now: datetime) -> None:
    with transaction(conn):
        for clinic in CLINICS.values():
            conn.execute(
                "INSERT INTO clinics (id, name, tz, policy_json) VALUES (?, ?, ?, ?)",
                (clinic.id, clinic.name, clinic.tz, json.dumps(clinic.policy())),
            )
            conn.executemany(
                "INSERT INTO doctors (id, clinic_id, name) VALUES (?, ?, ?)",
                [(doctor_id, clinic.id, name) for doctor_id, name in clinic.doctors.items()],
            )
            conn.executemany(
                "INSERT INTO slots (id, doctor_id, start_utc, end_utc) VALUES (?, ?, ?, ?)",
                list(slot_rows(clinic, now)),
            )
        conn.executemany("INSERT INTO customers (id, external_ref) VALUES (?, ?)", [(c, c) for c in CUSTOMERS])


def insert_fixtures(conn: sqlite3.Connection, now: datetime) -> dict:
    clinic = CLINICS["clinic_a"]
    monday = first_monday(clinic, now)
    friday, wednesday = monday + timedelta(days=4), monday + timedelta(days=2)
    with transaction(conn):
        full = create_booking(conn, clinic, "c_walkin", slot_id("dr_a", friday, time(11, 0)), now)
        edited = create_booking(conn, clinic, "c_walkin", slot_id("dr_b", wednesday, time(10, 0)), now)
    with transaction(conn):
        move_booking(conn, clinic, edited["booking_id"], slot_id("dr_b", wednesday, time(10, 30)), 1, now, "clinic")
    conflict = None
    try:
        with transaction(conn):
            move_booking(conn, clinic, edited["booking_id"], slot_id("dr_b", wednesday, time(11, 0)), 1, now, "clinic")
    except ClinicError as error:
        conflict = error.code
        log.info("seeded conflicting staff edit on %s rejected: %s", edited["ref"], error.code)
    return {"full_slot_booking": full["ref"], "edited_booking": edited["ref"], "stale_edit": conflict}


def seed(conn: sqlite3.Connection, clock: Clock) -> dict:
    if one(conn, "SELECT id FROM clinics LIMIT 1"):
        return {"seeded": False}
    now = clock.now()
    insert_reference_data(conn, now)
    return {"seeded": True, **insert_fixtures(conn, now)}


def reset(conn: sqlite3.Connection, clock: Clock) -> dict:
    with transaction(conn):
        for table in TABLES:
            conn.execute(f"DELETE FROM {table}")
    return seed(conn, clock)
