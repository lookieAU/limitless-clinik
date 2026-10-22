import json
from datetime import timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from agent.auth import current_auth
from agent.memory.lossy import LossySummarizer
from agent.memory.summarize import summarize
from agent.ui.routes import render
from agent.ui.view import panel_context
from shared.time import to_local

router = APIRouter(prefix="/admin")
AGENT_TABLES = (
    "claim_embeddings", "claims", "verified_state", "events", "processed_events", "poll_cursors", "outbox",
    "pending_offers", "pending_notices", "memory_summaries", "messages", "sessions",
)
MODES = ("none", "timeout_before_commit", "timeout_after_commit", "slow")


def result(request: Request, title: str, payload) -> HTMLResponse:
    response = HTMLResponse(f"<strong>{title}</strong><div class='result'>{json.dumps(payload, indent=2, default=str)}</div>")
    response.headers["HX-Trigger"] = "panels"
    return response


async def clinic_admin(request: Request, path: str, body: dict | None = None, params: dict | None = None) -> dict:
    response = await request.app.state.ctx.http.post(f"/admin/{path}", json=body, params=params)
    return {"status": response.status_code, "body": response.json()}


@router.get("", response_class=HTMLResponse)
async def admin_page(request: Request) -> Response:
    auth = current_auth(request)
    if auth is None:
        return RedirectResponse("/login", status_code=303)
    ctx = request.app.state.ctx
    return render(
        request,
        "admin.html",
        user=auth.user,
        modes=MODES,
        clinics=ctx.registry.adapters.keys(),
        enabled=ctx.registry.enabled_ids,
        **{**panel_context(ctx, auth.user), "now": ctx.clock.now()},
    )


@router.post("/act/cancel-slot", response_class=HTMLResponse)
async def cancel_slot(request: Request, slot_id: str = Form(...), deliver: str = Form("true")) -> HTMLResponse:
    return result(request, f"Clinic cancelled slot {slot_id}", await clinic_admin(request, f"slots/{slot_id}/cancel", params={"deliver": deliver}))


@router.post("/act/fill-slot", response_class=HTMLResponse)
async def fill_slot(request: Request, slot_id: str = Form(...)) -> HTMLResponse:
    return result(request, f"Clinic filled slot {slot_id}", await clinic_admin(request, f"slots/{slot_id}/fill"))


@router.post("/act/fault", response_class=HTMLResponse)
async def fault(request: Request, endpoint: str = Form(...), mode: str = Form(...)) -> HTMLResponse:
    return result(request, "Faults", await clinic_admin(request, "faults", {"endpoint": endpoint, "mode": mode}))


@router.post("/act/clock", response_class=HTMLResponse)
async def clock(request: Request, hours: float = Form(...)) -> HTMLResponse:
    ctx = request.app.state.ctx
    if not hasattr(ctx.clock, "advance"):
        return result(request, "Clock", {"error": "set DEMO_NOW to use an adjustable clock"})
    ctx.clock.advance(timedelta(hours=hours))
    clinic = await clinic_admin(request, "clock", {"seconds": hours * 3600})
    return result(request, f"Clock +{hours}h", {"agent_now": ctx.clock.now(), "clinic": clinic["body"]})


@router.post("/act/summary", response_class=HTMLResponse)
async def nightly_summary(request: Request, lossy: str = Form("no")) -> Response:
    auth = current_auth(request)
    if auth is None:
        return Response(status_code=401)
    ctx = request.app.state.ctx
    day = to_local(ctx.clock.now(), ZoneInfo(auth.user["tz"])).date()
    summary = await summarize(ctx, auth.user["id"], day, llm=LossySummarizer() if lossy == "yes" else None)
    title = "Summary kept" if summary.validated else "Summary REJECTED — previous validated memory kept"
    return result(request, title, {"day": summary.day_local, "prose": summary.prose, "errors": summary.errors, "structured": summary.structured["constraints"]})


@router.post("/act/clinic", response_class=HTMLResponse)
async def toggle_clinic(request: Request, clinic_id: str = Form(...), enabled: str = Form(...)) -> HTMLResponse:
    ctx = request.app.state.ctx
    ctx.registry.set_enabled(clinic_id, enabled == "yes")
    return result(request, "Enabled clinics", {"enabled": ctx.registry.enabled_ids})


@router.post("/act/reset", response_class=HTMLResponse)
async def reset(request: Request) -> HTMLResponse:
    ctx = request.app.state.ctx
    clinic = await clinic_admin(request, "reset")
    for table in AGENT_TABLES:
        ctx.conn.execute(f"DELETE FROM {table}")
    ctx.registry.enabled_ids = list(ctx.settings.enabled_clinics)
    ctx.doctor_cache.clear()
    return result(request, "Reset clinic and agent data (sign in again)", clinic["body"])
