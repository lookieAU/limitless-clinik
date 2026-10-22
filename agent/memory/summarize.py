import argparse
import asyncio
import json
from dataclasses import dataclass
from datetime import date, time, timedelta
from zoneinfo import ZoneInfo

from agent import outbox
from agent.llm.types import LLMProvider, SummaryRequest
from agent.memory.validate_summary import Validation, validate_summary
from agent.repo import claims, users, verified
from agent.repo.audit import log_event
from shared.ids import new_id
from shared.time import local_to_utc, to_iso_z

CONSTRAINT_SUBJECTS = ("day", "date", "time_window", "week", "doctor", "clinic")


@dataclass
class Summary:
    id: str
    user_id: str
    day_local: str
    structured: dict
    prose: str
    validated: bool
    errors: list[str]


def day_bounds(day: date, tz: ZoneInfo) -> tuple[str, str]:
    return to_iso_z(local_to_utc(day, time(0, 0), tz)), to_iso_z(local_to_utc(day + timedelta(days=1), time(0, 0), tz))


def constraint(row: dict) -> dict:
    return {
        "subject": row["subject"],
        "value": row["value"],
        "polarity": row["polarity"],
        "claim_ids": [row["id"]],
        "raw": row["raw_text"],
        "lang": row["lang"],
    }


def build_structured(conn, user: dict, day: date) -> dict:
    tz = ZoneInfo(user["tz"])
    rows = [row for row in claims.in_window(conn, user["id"], *day_bounds(day, tz)) if row["subject"] in CONSTRAINT_SUBJECTS]
    return {
        "day_local": day.isoformat(),
        "tz": user["tz"],
        "constraints": [constraint(row) for row in rows if row["status"] in claims.LIVE],
        "open_intents": [{"intent": row["action"], "state": row["state"]} for row in outbox.unknown_for_user(conn, user["id"])],
        "clinic_snapshot": [
            {"booking_id": row["booking_id"], "ref": row["ref"], "status": row["status"], "observed_utc": row["observed_utc"], "note": "re-verify before use"}
            for row in verified.for_customer(conn, user["customer_id"])
        ],
        "overridden": [constraint(row) | {"event": row["overridden_by_event"]} for row in rows if row["status"] == "overridden"],
    }


def store(conn, user: dict, structured: dict, prose: str, validation: Validation, now) -> Summary:
    summary = Summary(new_id("sum"), user["id"], structured["day_local"], structured, prose, validation.ok, validation.errors)
    conn.execute(
        "INSERT INTO memory_summaries (id, user_id, day_local, structured_json, prose, lang, validated, errors_json, created_utc) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (summary.id, user["id"], summary.day_local, json.dumps(structured), prose, user["preferred_lang"], int(validation.ok), json.dumps(validation.errors), to_iso_z(now)),
    )
    return summary


async def summarize(ctx, user_id: str, day: date, llm: LLMProvider | None = None) -> Summary:
    user = users.get_user(ctx.conn, user_id) or users.by_customer(ctx.conn, user_id)
    provider = llm or ctx.llm
    structured = build_structured(ctx.conn, user, day)
    lang = user["preferred_lang"]
    prose = await provider.summarize(SummaryRequest(structured=structured, lang=lang))
    validation = validate_summary(structured, prose)
    if not validation.ok:
        log_event(ctx.conn, ctx.clock.now(), "summary_rejected", {"day": day.isoformat(), "errors": validation.errors, "attempt": 1}, user["id"])
        prose = await provider.summarize(SummaryRequest(structured=structured, lang=lang, strict=True))
        validation = validate_summary(structured, prose)
        if not validation.ok:
            log_event(ctx.conn, ctx.clock.now(), "summary_rejected", {"day": day.isoformat(), "errors": validation.errors, "attempt": 2}, user["id"])
    summary = store(ctx.conn, user, structured, prose, validation, ctx.clock.now())
    if validation.ok:
        log_event(ctx.conn, ctx.clock.now(), "summary_written", {"day": day.isoformat(), "summary_id": summary.id}, user["id"])
    ctx.bus.publish(user["id"], "panels")
    return summary


async def main() -> None:
    from agent.context import build_context

    parser = argparse.ArgumentParser(description="Write one customer's nightly memory summary")
    parser.add_argument("--user", required=True, help="user id (u_asha) or customer id (c_asha)")
    parser.add_argument("--date", required=True, help="local day, YYYY-MM-DD")
    args = parser.parse_args()
    ctx = build_context()
    summary = await summarize(ctx, args.user, date.fromisoformat(args.date))
    print(json.dumps({"id": summary.id, "validated": summary.validated, "errors": summary.errors, "prose": summary.prose}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
