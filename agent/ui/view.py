from zoneinfo import ZoneInfo

from agent.memory.load import load_memory
from agent.repo import claims, verified
from agent.repo.audit import recent_events
from agent.vocab import claim_label
from shared.sqlite import many
from shared.time import format_dual, parse_utc


def ago(ctx, stamp: str) -> str:
    seconds = int((ctx.clock.now() - parse_utc(stamp)).total_seconds())
    if seconds < 10:
        return "just now"
    if seconds < 120:
        return f"{seconds}s ago"
    if seconds < 7200:
        return f"{seconds // 60} min ago"
    if seconds < 172800:
        return f"{seconds // 3600} h ago"
    return f"{seconds // 86400} days ago"


def verified_rows(ctx, user: dict) -> list[dict]:
    rows = []
    for row in verified.for_customer(ctx.conn, user["customer_id"]):
        tz = ctx.registry.get(row["clinic_id"]).tz
        rows.append(
            {
                **row,
                "when": format_dual(parse_utc(row["slot"]["start_utc"]), tz, ZoneInfo(user["tz"])),
                "observed_ago": ago(ctx, row["observed_utc"]),
                "fresh": verified.is_fresh(row, ctx.clock.now(), ctx.settings.freshness_ttl_s, None) or row["source"] == "api",
            }
        )
    return rows


def claim_rows(ctx, user: dict) -> list[dict]:
    return [
        {**row, "label": claim_label(row, "en"), "said_ago": ago(ctx, row["created_utc"])}
        for row in claims.all_for_user(ctx.conn, user["id"], limit=40)
    ]


def summary_rows(ctx, user: dict) -> dict:
    memory = load_memory(ctx.conn, user["id"])
    history = many(
        ctx.conn,
        "SELECT id, day_local, validated, prose, errors_json, created_utc FROM memory_summaries WHERE user_id = ? ORDER BY rowid DESC LIMIT 4",
        (user["id"],),
    )
    return {"active": memory.summary_id, "items": history}


def panel_context(ctx, user: dict) -> dict:
    return {
        "verified": verified_rows(ctx, user),
        "claims": claim_rows(ctx, user),
        "events": recent_events(ctx.conn, user["id"], 30),
        "summaries": summary_rows(ctx, user),
        "now": ctx.clock.now().isoformat(timespec="seconds"),
        "ttl": int(ctx.settings.freshness_ttl_s),
    }


def paragraphs(reply: str) -> list[str]:
    return [part for part in reply.split("\n\n") if part.strip()]
