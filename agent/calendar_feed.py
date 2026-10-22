from fastapi import APIRouter, HTTPException, Request, Response
from icalendar import Calendar, Event

from agent.repo import users, verified
from shared.time import parse_utc

router = APIRouter()
STATUS = {"confirmed": "CONFIRMED", "cancelled": "CANCELLED"}


def build_feed(conn, user: dict) -> bytes:
    calendar = Calendar()
    calendar.add("prodid", "-//Clinik by Limitless//booking-agent//EN")
    calendar.add("version", "2.0")
    calendar.add("x-wr-calname", "Clinik appointments")
    for row in verified.for_customer(conn, user["customer_id"]):
        event = Event()
        event.add("uid", f"{row['booking_id']}@booking-agent")
        event.add("dtstart", parse_utc(row["slot"]["start_utc"]))
        event.add("dtend", parse_utc(row["slot"]["end_utc"]))
        event.add("dtstamp", parse_utc(row["observed_utc"]))
        event.add("summary", f"{row['slot']['doctor_name']} ({row['ref']})")
        event.add("status", STATUS[row["status"]])
        event.add("sequence", row["version"])
        event.add("x-source", f"clinic, observed {row['observed_utc']}")
        calendar.add_component(event)
    return calendar.to_ical()


@router.get("/calendar/{token}.ics")
async def calendar_feed(token: str, request: Request) -> Response:
    ctx = request.app.state.ctx
    user = users.by_ics_token(ctx.conn, token)
    if user is None:
        raise HTTPException(status_code=404, detail="unknown calendar")
    return Response(build_feed(ctx.conn, user), media_type="text/calendar")
