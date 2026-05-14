"""
Real-time WebSocket hub.

Agents and the sensor publish lifecycle events to this hub; the frontend
subscribes once and receives a live stream of pipeline activity.

Channels (string `topic` field on every message):
  - "system"        — startup, healthchecks, weight updates
  - "ingest"        — event accepted
  - "correlate"     — incident created/updated
  - "score"         — risk computed
  - "explain"       — explanation generated
  - "feedback"      — analyst verdict applied
  - "sensor"        — sensor status / flow stats
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.core.logging import logger

router = APIRouter(prefix="/api/rt", tags=["realtime"])


class _Hub:
    def __init__(self) -> None:
        self._clients: Set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._clients.add(ws)
        await ws.send_text(
            json.dumps({"topic": "system", "msg": "hello", "ts": time.time()})
        )

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients.discard(ws)

    async def publish(self, topic: str, payload: dict[str, Any]) -> None:
        msg = json.dumps({"topic": topic, "ts": time.time(), **payload})
        dead: list[WebSocket] = []
        for ws in list(self._clients):
            try:
                await ws.send_text(msg)
            except Exception:
                dead.append(ws)
        if dead:
            async with self._lock:
                for ws in dead:
                    self._clients.discard(ws)


hub = _Hub()


@router.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await hub.connect(ws)
    try:
        while True:
            try:
                await asyncio.wait_for(ws.receive_text(), timeout=60)
            except asyncio.TimeoutError:
                # Keep-alive ping
                try:
                    await ws.send_text(
                        json.dumps({"topic": "system", "msg": "ping", "ts": time.time()})
                    )
                except Exception:
                    break
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning(f"WebSocket error: {e}")
    finally:
        await hub.disconnect(ws)


# Convenience helper used from agents
async def emit(topic: str, **payload: Any) -> None:
    try:
        await hub.publish(topic, payload)
    except Exception as e:
        logger.debug(f"emit({topic}) swallowed error: {e}")