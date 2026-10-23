from datetime import timedelta
from html import escape
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from agent.auth import current_auth
from agent.memory.lossy import LossySummarizer
from agent.memory.summarize import summarize
from agent.repo import verified
from agent.ui.routes import render
from agent.ui.view import activity, panel_context
from shared.time import to_local

router = APIRouter(prefix="/admin")
AGENT_TABLES = (
    "claim_embeddings", "claims", "verified_state", "events", "processed_events", "poll_cursors", "outbox",
    "pending_offers", "pending_notices", "memory_summaries", "messages", "sessions",
)
FAULTS = {
    "timeout_before_commit": "The next booking request will time out before the clinic saves it.",
    "timeout_after_commit": "The next booking request will be saved by the clinic, but the reply will time out.",
    "none": "Booking requests are back to normal.",
}


def say(text: str) -> HTMLResponse:
    return HTMLResponse(escape(text))


async def clinic_admin(request: Request, path: str, body: dict | None = None, params: dict | None = None) -> dict:
    response = await request.app.state.ctx.http.post(f"/admin/{path}", json=body, params=params)
    response.raise_for_status()
    return response.json()


@router.get("", response_class=HTMLResponse)
async def admin_page(request: Request) -> Response:
    auth = current_auth(request)
    if auth is None:
        return RedirectResponse("/login", status_code=303)
    ctx = request.app.state.ctx
    return render(request, "admin.html", user=auth.user, activity=activity(ctx, auth.user), **panel_context(ctx, auth.user))


@router.get("/activity", response_class=HTMLResponse)
async def activity_feed(request: Request) -> Response:
    auth = current_auth(request)
    if auth is None:
        return Response(status_code=401)
    return render(request, "_activity.html", activity=activity(request.app.state.ctx, auth.user))


@router.post("/act/cancel-slot", response_class=HTMLResponse)
async def cancel_slot(request: Request, ref: str = Form(...), deliver: str = Form("true")) -> Response:
    auth = current_auth(request)
    row = verified.by_ref(request.app.state.ctx.conn, auth.user["customer_id"], ref) if auth else None
    if row is None:
        return say("Booking not found.")
    result = await clinic_admin(request, f"slots/{row['slot']['id']}/cancel", params={"deliver": deliver})
    if result["delivered"]:
        return say(f"The clinic cancelled {ref} and sent a webhook. Go back to the chat and say hi.")
    return say(f"The clinic cancelled {ref}, but the webhook was lost. The agent will find out when it next checks with the clinic.")


@router.post("/act/fault", response_class=HTMLResponse)
async def fault(request: Request, mode: str = Form(...)) -> Response:
    await clinic_admin(request, "faults", {"endpoint": "book", "mode": mode})
    return say(FAULTS.get(mode, "Done."))


@router.post("/act/clock", response_class=HTMLResponse)
async def clock(request: Request, hours: float = Form(...)) -> Response:
    ctx = request.app.state.ctx
    if not hasattr(ctx.clock, "advance"):
        return say("Set DEMO_NOW in .env to use time travel.")
    ctx.clock.advance(timedelta(hours=hours))
    await clinic_admin(request, "clock", {"seconds": hours * 3600})
    return say(f"Moved forward {hours:g} hours. It's now {ctx.clock.now():%a %d %b, %H:%M} UTC. Switch mode to start a new conversation.")


@router.post("/act/summary", response_class=HTMLResponse)
async def nightly_summary(request: Request, lossy: str = Form("no")) -> Response:
    auth = current_auth(request)
    if auth is None:
        return Response(status_code=401)
    ctx = request.app.state.ctx
    day = to_local(ctx.clock.now(), ZoneInfo(auth.user["tz"])).date()
    summary = await summarize(ctx, auth.user["id"], day, llm=LossySummarizer() if lossy == "yes" else None)
    if summary.validated:
        return say(f"Saved: “{summary.prose}”")
    return say(f"Rejected: “{summary.prose}” — {'; '.join(summary.errors)}. The previous memory is kept.")


@router.post("/act/clinic", response_class=HTMLResponse)
async def toggle_clinic(request: Request, enabled: str = Form(...)) -> Response:
    ctx = request.app.state.ctx
    ctx.registry.set_enabled("clinic_b", enabled == "yes")
    ctx.doctor_cache.clear()
    names = ", ".join(adapter.policy.name for adapter in ctx.registry.enabled())
    return say(f"Clinics now available: {names}.")


@router.post("/act/reset", response_class=HTMLResponse)
async def reset(request: Request) -> Response:
    ctx = request.app.state.ctx
    await clinic_admin(request, "reset")
    for table in AGENT_TABLES:
        ctx.conn.execute(f"DELETE FROM {table}")
    ctx.registry.enabled_ids = list(ctx.settings.enabled_clinics)
    ctx.doctor_cache.clear()
    return HTMLResponse('Everything was reset. <a href="/login">Sign in again</a>.')
