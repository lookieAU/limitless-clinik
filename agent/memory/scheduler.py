import asyncio
import logging
from datetime import date, time
from zoneinfo import ZoneInfo

from agent.memory.summarize import summarize
from agent.repo import users
from shared.sqlite import many
from shared.time import parse_utc, to_local

log = logging.getLogger("agent.scheduler")
CUTOFF = time(23, 59)


def due_days(conn, user: dict, now) -> list[date]:
    tz = ZoneInfo(user["tz"])
    local_now = to_local(now, tz)
    done = {row["day_local"] for row in many(conn, "SELECT day_local FROM memory_summaries WHERE user_id = ?", (user["id"],))}
    days = {to_local(parse_utc(row["created_utc"]), tz).date() for row in many(conn, "SELECT created_utc FROM claims WHERE user_id = ?", (user["id"],))}
    eligible = {day for day in days if day < local_now.date() or (day == local_now.date() and local_now.time() >= CUTOFF)}
    return sorted(day for day in eligible if day.isoformat() not in done)


async def run_due(ctx) -> list[str]:
    written = []
    for user in users.list_users(ctx.conn):
        for day in due_days(ctx.conn, user, ctx.clock.now()):
            summary = await summarize(ctx, user["id"], day)
            written.append(summary.id)
    return written


async def scheduler_loop(ctx, interval_s: float = 60.0) -> None:
    while True:
        try:
            await run_due(ctx)
        except Exception:
            log.exception("nightly summary run failed")
        await asyncio.sleep(interval_s)
