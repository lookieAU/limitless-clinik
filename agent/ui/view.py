import json
from zoneinfo import ZoneInfo

from agent.repo import claims, messages, verified
from agent.repo.audit import recent_events
from agent.vocab import value_label
from shared.time import format_dual, parse_utc

ACTIVITY = {
    "injection_flag": "Prompt-injection attempt spotted — treated as plain text, nothing executed",
    "gate_refused": "Policy gate blocked a tool call ({code})",
    "reply_blocked": "Model tried to state a status it hadn't verified — blocked and re-checked",
    "authz_denied": "Attempt to touch another customer's booking — denied",
    "summary_rejected": "Nightly summary rejected: {errors}",
    "summary_written": "Nightly summary saved",
    "clarification_asked": "Asked one clarifying question; changes locked until answered",
    "clarification_resolved": "Clarification answered",
    "webhook_received": "Clinic webhook received ({type})",
    "clinic_change": "Clinic changed booking {ref} ({transition}) — earlier claims overridden",
    "clinic_write": "Sent a {action} to the clinic",
    "write_unknown": "Clinic timed out — checking before any retry",
    "reconciled": "Reconciled with the clinic (found: {found})",
    "status_recheck": "Re-checked booking status with the clinic",
    "notices_delivered": "Told the customer about a clinic change first",
    "offer_accepted": "Customer accepted an offered slot",
}


def ago(ctx, stamp: str) -> str:
    seconds = int((ctx.clock.now() - parse_utc(stamp)).total_seconds())
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{seconds // 60} min ago"
    if seconds < 86400:
        return f"{seconds // 3600} h ago"
    return f"{seconds // 86400} d ago"


def appointments(ctx, user: dict) -> list[dict]:
    rows = []
    for row in verified.for_customer(ctx.conn, user["customer_id"]):
        tz = ctx.registry.get(row["clinic_id"]).tz
        when = format_dual(parse_utc(row["slot"]["start_utc"]), tz, ZoneInfo(user["tz"]))
        rows.append({"ref": row["ref"], "status": row["status"], "doctor": row["slot"]["doctor_name"], "when": when, "checked": ago(ctx, row["observed_utc"])})
    return rows


def told_us(ctx, user: dict) -> list[dict]:
    rows = claims.live_for_user(ctx.conn, user["id"])
    return [
        {"label": value_label(row["subject"], row["value"], "en"), "negative": row["polarity"] == "negative", "raw": row["raw_text"]}
        for row in reversed(rows)
        if row["subject"] != "booking_ref"
    ]


def panel_context(ctx, user: dict) -> dict:
    return {"appointments": appointments(ctx, user), "told_us": told_us(ctx, user)}


def describe(event: dict) -> str | None:
    template = ACTIVITY.get(event["type"])
    if template is None:
        return None
    payload = {key: (", ".join(value) if isinstance(value, list) else value) for key, value in event["payload"].items()}
    try:
        return template.format(**payload)
    except (KeyError, IndexError):
        return template.split(" (")[0].split(":")[0]


def activity(ctx, user: dict) -> list[dict]:
    items = []
    for event in recent_events(ctx.conn, user["id"], 60):
        text = describe(event)
        if text:
            items.append({"time": event["created_utc"][11:16], "text": text, "type": event["type"]})
    return items[:25]


def reply_view(text: str, result: dict | None) -> dict:
    result = result or {}
    return {
        "paragraphs": [part for part in text.split("\n\n") if part.strip()],
        "chips": result.get("chips", []),
        "tools": result.get("tools", []),
    }


def history(ctx, session_id: str) -> list[dict]:
    rows = messages.transcript(ctx.conn, session_id)
    pairs = []
    for index, row in enumerate(rows):
        if row["role"] != "customer":
            continue
        result = json.loads(row["result_json"]) if row["result_json"] else None
        agent = rows[index + 1] if index + 1 < len(rows) and rows[index + 1]["role"] == "agent" else None
        pairs.append({"text": row["text"], "reply": reply_view(agent["text"], result) if agent else None})
    return pairs
