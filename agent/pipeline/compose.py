from datetime import datetime
from zoneinfo import ZoneInfo

from agent.pipeline.state import ORDER, Segment, TurnState
from agent.pipeline.templates import text
from agent.repo import claims as claims_repo
from agent.repo import verified
from agent.vocab import claim_label
from shared.time import format_clock, format_dual, parse_utc, to_local, tz_label


def ago(lang: str, observed: datetime, now: datetime) -> str:
    seconds = int((now - observed).total_seconds())
    if seconds < 10:
        return text(lang, "ago.now")
    if seconds < 120:
        return text(lang, "ago.seconds", n=seconds)
    return text(lang, "ago.minutes", n=seconds // 60)


def when(state: TurnState, start_utc: str, clinic_id: str) -> str:
    clinic_tz = state.ctx.registry.get(clinic_id).tz
    return format_dual(parse_utc(start_utc), clinic_tz, ZoneInfo(state.user["tz"]))


def booking_params(state: TurnState, row: dict) -> dict:
    return {
        "doctor": row["slot"]["doctor_name"],
        "when": when(state, row["slot"]["start_utc"], row["clinic_id"]),
        "ref": row["ref"],
        "ago": ago(state.lang, parse_utc(row["observed_utc"]), state.ctx.clock.now()),
    }


def notice_params(state: TurnState, params: dict) -> dict:
    tz = ZoneInfo(state.user["tz"])
    at = to_local(parse_utc(params["at"]), tz)
    return {
        "doctor": params["doctor"],
        "when": when(state, params["start_utc"], params["clinic_id"]),
        "ref": params["ref"],
        "source": text(state.lang, f"source.{params['source']}"),
        "at": f"{at:%d %b} {format_clock(at)} {tz_label(tz)}",
    }


def render_segment(state: TurnState, segment: Segment) -> str:
    if segment.kind == "prose":
        return segment.params["text"]
    if segment.kind == "notice":
        return text(state.lang, segment.key, **notice_params(state, segment.params))
    if segment.kind in ("status", "action"):
        row = verified.get(state.conn, segment.booking_id)
        key = segment.key
        if segment.kind == "status" or (key != "action.cancelled" and row["status"] != "confirmed"):
            key = f"status.{row['status']}"
        return text(state.lang, key, **booking_params(state, row))
    return text(state.lang, segment.key, **segment.params)


def render(state: TurnState) -> str:
    segments = list(state.segments)
    if state.prose.strip():
        segments.append(Segment("prose", "prose", {"text": state.prose.strip()}))
    ordered = sorted(segments, key=lambda s: ORDER.index(s.kind))
    return "\n\n".join(render_segment(state, segment) for segment in ordered)


def system_text(state: TurnState) -> str:
    ordered = sorted(state.segments, key=lambda s: ORDER.index(s.kind))
    return "\n".join(render_segment(state, segment) for segment in ordered)


def verified_fact(state: TurnState, row: dict) -> dict:
    local = format_dual(parse_utc(row["slot"]["start_utc"]), state.ctx.registry.get(row["clinic_id"]).tz, ZoneInfo(state.user["tz"]))
    return {
        "id": f"v:{row['booking_id']}",
        "kind": "verified",
        "source": row["source"],
        "at_utc": row["observed_utc"],
        "text": f"{row['ref']} {row['status']} — {row['slot']['doctor_name']}, {local}",
    }


def facts(state: TurnState) -> list[dict]:
    rows = [verified.get(state.conn, booking_id) for booking_id in dict.fromkeys(state.booking_ids())]
    claimed = claims_repo.live_for_session(state.conn, state.session_id)
    return [verified_fact(state, row) for row in rows if row] + [
        {
            "id": f"c:{claim['id']}",
            "kind": "claimed",
            "source": claim["source"],
            "at_utc": claim["created_utc"],
            "text": f"{claim_label(claim, 'en')} (said: \"{claim['raw_text']}\")",
        }
        for claim in claimed
    ]
