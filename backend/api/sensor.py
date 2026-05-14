"""
Sensor control API.

The sensor is a long-running task started/stopped by the analyst from the UI.
It generates plausible flow events at a steady cadence so the UI lights up
even on a sandboxed dev box without raw capture privileges.

Endpoints:
  POST /api/sensor/start    → {running, mode, started_at}
  POST /api/sensor/stop     → {running}
  GET  /api/sensor/status   → {running, mode, started_at, events_emitted}
"""
from __future__ import annotations

import asyncio
import os
import random
import time
import uuid
from dataclasses import dataclass
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.api.realtime import emit
from backend.core.logging import logger
from backend.core.security import ROLE_ANALYST, require_roles
from backend.db.postgres import async_session_factory
from backend.models.models import Incident

router = APIRouter(prefix="/api/sensor", tags=["sensor"])


@dataclass
class SensorState:
    task: Optional[asyncio.Task] = None
    started_at: Optional[float] = None
    events_emitted: int = 0
    mode: str = "off"  # off | live | simulated


state = SensorState()


async def _simulated_loop() -> None:
    """Generate plausible flow events through the full agent pipeline."""
    from backend.agents.correlation_agent import correlation_agent
    from backend.agents.explanation_agent import explanation_agent
    from backend.agents.ingestion_agent import ingestion_agent
    from backend.agents.risk_agent import risk_agent

    attackers = ["203.0.113.42", "198.51.100.77", "185.220.101.45", "203.0.113.99"]
    victims = ["10.0.0.5", "10.0.0.12", "10.0.0.14", "192.0.2.10", "192.0.2.25"]
    types = [
        ("port_scan", 0.5, "Probe across multiple ports"),
        ("brute_force", 0.7, "Repeated authentication failures"),
        ("c2", 0.8, "Periodic beaconing pattern"),
        ("exfil", 0.9, "Anomalously large outbound transfer"),
        ("lateral_movement", 0.75, "SMB authentication from compromised host"),
    ]

    while True:
        try:
            t = random.choice(types)
            evt = {
                "source": "live_sensor",
                "event_type": t[0],
                "src_ip": random.choice(attackers),
                "dst_ip": random.choice(victims),
                "src_port": random.randint(1024, 65535),
                "dst_port": random.choice([22, 80, 443, 445, 3306, 3389]),
                "protocol": "tcp",
                "severity": min(0.95, t[1] + random.random() * 0.15),
                "description": t[2],
                "raw": {"flow_id": str(uuid.uuid4())},
            }
            await emit("sensor", action="flow_detected", **evt)

            async with async_session_factory() as session:
                event = await ingestion_agent.handle(evt, session)
                incident, chain = await correlation_agent.handle(event, session)
                q = await session.execute(
                    select(Incident)
                    .options(selectinload(Incident.events))
                    .where(Incident.id == incident.id)
                )
                incident = q.scalar_one()
                await risk_agent.handle(incident, chain, session)
                await explanation_agent.handle(incident, chain, session)
                await session.commit()
            state.events_emitted += 1

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning(f"Sensor loop iteration failed: {e}")

        await asyncio.sleep(random.uniform(8.0, 15.0))


@router.post("/start", dependencies=[Depends(require_roles(*ROLE_ANALYST))])
async def start_sensor():
    if state.task and not state.task.done():
        return {
            "running": True,
            "mode": state.mode,
            "started_at": state.started_at,
        }
    state.events_emitted = 0
    state.started_at = time.time()
    state.mode = os.getenv("AUTOCTI_SENSOR_MODE", "simulated")
    state.task = asyncio.create_task(_simulated_loop())
    await emit("sensor", action="started", mode=state.mode, started_at=state.started_at)
    logger.info(f"Sensor started (mode={state.mode})")
    return {
        "running": True,
        "mode": state.mode,
        "started_at": state.started_at,
    }


@router.post("/stop", dependencies=[Depends(require_roles(*ROLE_ANALYST))])
async def stop_sensor():
    if state.task and not state.task.done():
        state.task.cancel()
        try:
            await state.task
        except asyncio.CancelledError:
            pass
    state.task = None
    state.mode = "off"
    await emit("sensor", action="stopped")
    logger.info("Sensor stopped")
    return {"running": False}


@router.get("/status", dependencies=[Depends(require_roles(*ROLE_ANALYST))])
async def status():
    return {
        "running": bool(state.task and not state.task.done()),
        "mode": state.mode,
        "started_at": state.started_at,
        "events_emitted": state.events_emitted,
    }