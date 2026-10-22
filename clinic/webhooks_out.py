import asyncio
import hashlib
import hmac
import json
import logging
import sqlite3

import httpx

from clinic.clinics import CLINICS
from shared.clock import Clock
from shared.time import to_iso_z

log = logging.getLogger("clinic.webhooks")


def sign(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


class WebhookSender:
    def __init__(
        self,
        conn: sqlite3.Connection,
        client: httpx.AsyncClient,
        url: str,
        secret: str,
        clock: Clock,
        backoff: tuple[float, ...],
    ):
        self.conn = conn
        self.client = client
        self.url = url
        self.secret = secret
        self.clock = clock
        self.backoff = backoff

    async def deliver_all(self, events: list[dict]) -> list[str]:
        delivered = []
        for event in events:
            if CLINICS[event["clinic_id"]].delivery == "webhook" and await self.deliver(event):
                delivered.append(event["event_id"])
        return delivered

    async def deliver(self, event: dict) -> bool:
        body = json.dumps(event).encode()
        headers = {"Content-Type": "application/json", "X-Signature": sign(self.secret, body)}
        for attempt, pause in enumerate((0.0, *self.backoff), start=1):
            if pause:
                await asyncio.sleep(pause)
            self.conn.execute("UPDATE events SET attempts = ? WHERE id = ?", (attempt, event["event_id"]))
            try:
                response = await self.client.post(self.url, content=body, headers=headers)
            except httpx.HTTPError as error:
                log.warning("webhook %s attempt %s failed: %s", event["event_id"], attempt, error)
                continue
            if response.status_code < 300:
                self.conn.execute(
                    "UPDATE events SET delivered_utc = ? WHERE id = ?", (to_iso_z(self.clock.now()), event["event_id"])
                )
                return True
            log.warning("webhook %s attempt %s got %s", event["event_id"], attempt, response.status_code)
        return False
