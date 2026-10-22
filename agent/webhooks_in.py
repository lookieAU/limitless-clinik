import hashlib
import hmac
import json

from fastapi import APIRouter, HTTPException, Request

from agent.pipeline.sync import apply_event
from agent.repo.audit import log_event

router = APIRouter()


def valid_signature(secret: str, body: bytes, signature: str | None) -> bool:
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return bool(signature) and hmac.compare_digest(expected, signature)


@router.post("/webhooks/clinic")
async def clinic_webhook(request: Request) -> dict:
    ctx = request.app.state.ctx
    body = await request.body()
    if not valid_signature(ctx.settings.webhook_secret, body, request.headers.get("X-Signature")):
        log_event(ctx.conn, ctx.clock.now(), "webhook_rejected", {"reason": "bad_signature"})
        raise HTTPException(status_code=401, detail="bad signature")
    raw = json.loads(body)
    clinic_id = raw.get("clinic_id", "")
    if clinic_id not in ctx.registry.adapters:
        raise HTTPException(status_code=404, detail="unknown clinic")
    event = ctx.registry.get(clinic_id).normalize_event(raw)
    if event is None:
        return {"status": "ignored"}
    outcome = apply_event(ctx, event, "webhook")
    user_row = ctx.conn.execute("SELECT id FROM users WHERE customer_id = ?", (event.booking.customer_id,)).fetchone()
    log_event(
        ctx.conn,
        ctx.clock.now(),
        "webhook_received",
        {"event_id": event.event_id, "type": event.type.value, "ref": event.booking.ref, "version": event.booking.version, "outcome": outcome},
        user_row["id"] if user_row else None,
    )
    return {"status": outcome}
