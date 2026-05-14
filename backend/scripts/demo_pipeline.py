"""
End-to-end SOC-pipeline demo.

Synthesises a small set of realistic events, runs them through all five
agents, and prints a summary of the resulting incidents.

Usage:
    python -m backend.scripts.demo_pipeline
"""
from __future__ import annotations

import asyncio
import random
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.agents.correlation_agent import correlation_agent
from backend.agents.explanation_agent import explanation_agent
from backend.agents.ingestion_agent import ingestion_agent
from backend.agents.risk_agent import risk_agent
from backend.core.logging import logger, setup_logging
from backend.db.chroma_client import vector_store
from backend.db.neo4j_client import neo4j_client
from backend.db.postgres import async_session_factory, init_db
from backend.models.models import Incident

SAMPLE_EVENTS = [
    {
        "source": "suricata",
        "event_type": "port_scan",
        "src_ip": "185.199.108.77",
        "dst_ip": "10.0.0.14",
        "src_port": 51234,
        "dst_port": 22,
        "protocol": "tcp",
        "severity": 0.6,
        "description": "Port scan detected from external host",
    },
    {
        "source": "suricata",
        "event_type": "brute_force",
        "src_ip": "185.199.108.77",
        "dst_ip": "10.0.0.14",
        "src_port": 52000,
        "dst_port": 22,
        "protocol": "tcp",
        "severity": 0.75,
        "description": "40 failed SSH logins in 2 minutes",
    },
    {
        "source": "endpoint",
        "event_type": "exploit",
        "src_ip": "185.199.108.77",
        "dst_ip": "10.0.0.14",
        "protocol": "tcp",
        "severity": 0.9,
        "description": "CVE-2023-0464 exploit attempt observed on webapp",
    },
    {
        "source": "firewall",
        "event_type": "c2",
        "src_ip": "10.0.0.14",
        "dst_ip": "203.0.113.9",
        "dst_port": 443,
        "protocol": "tcp",
        "severity": 0.85,
        "description": "Beaconing to known C2 domain",
    },
    {
        "source": "netflow",
        "event_type": "exfil",
        "src_ip": "10.0.0.14",
        "dst_ip": "203.0.113.9",
        "dst_port": 443,
        "protocol": "tcp",
        "severity": 0.95,
        "description": "Large outbound transfer (480 MB) to external IP",
    },
    # Independent benign scan from another IP — should become its own incident
    {
        "source": "suricata",
        "event_type": "scan",
        "src_ip": "198.51.100.5",
        "dst_ip": "10.0.0.50",
        "dst_port": 80,
        "protocol": "tcp",
        "severity": 0.2,
        "description": "Single HTTP probe",
    },
]


async def run() -> None:
    setup_logging()
    await init_db()
    await neo4j_client.connect()
    vector_store.connect()

    random.seed(42)
    async with async_session_factory() as session:
        for raw in SAMPLE_EVENTS:
            logger.info(f"── Processing: {raw['event_type']} {raw['src_ip']}→{raw['dst_ip']}")
            event = await ingestion_agent.handle(raw, session)
            inc, chain = await correlation_agent.handle(event, session)

            q = await session.execute(
                select(Incident)
                .options(selectinload(Incident.events))
                .where(Incident.id == inc.id)
            )
            inc = q.scalar_one()

            await risk_agent.handle(inc, chain, session)
            await explanation_agent.handle(inc, chain, session)
            await session.commit()

        # Print summary
        q = await session.execute(
            select(Incident).options(selectinload(Incident.events)).order_by(
                Incident.risk_score.desc()
            )
        )
        incs = list(q.scalars().all())

        print("\n" + "=" * 78)
        print(f"DEMO COMPLETE — {len(incs)} incident(s)")
        print("=" * 78)
        for i in incs:
            print(
                f"\n[{i.risk_score:.3f}]  {i.title}  (status={i.status}, "
                f"events={len(i.events)}, tactics={i.tactics})"
            )
            print(f"  Explanation: {i.explanation[:300].strip()}...")
            print(f"  Actions: {i.recommended_actions}")

    await neo4j_client.close()


if __name__ == "__main__":
    asyncio.run(run())
