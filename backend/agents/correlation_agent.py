"""
Agent 2 — Correlation & Hypothesis.

* Pushes every event into Neo4j.
* Groups events sharing an IP / time window into an Incident.
* Uses networkx for in-memory clustering (weakly connected components).
* Reconstructs the attack chain by ordering events chronologically.
* Tags MITRE ATT&CK tactics heuristically from event_type.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

import networkx as nx
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.logging import logger
from backend.db.neo4j_client import neo4j_client
from backend.models.models import Event, Incident


# Heuristic ATT&CK mapping — extend as needed
ATTACK_TACTIC_MAP = {
    "scan": ["Reconnaissance"],
    "port_scan": ["Reconnaissance"],
    "brute_force": ["Credential Access"],
    "exploit": ["Initial Access", "Execution"],
    "malware": ["Execution", "Defense Evasion"],
    "lateral_movement": ["Lateral Movement"],
    "c2": ["Command and Control"],
    "exfil": ["Exfiltration"],
    "ddos": ["Impact"],
    "privilege_escalation": ["Privilege Escalation"],
}


def tactics_for(event_type: str) -> List[str]:
    key = event_type.lower().replace("-", "_")
    return ATTACK_TACTIC_MAP.get(key, [])


class CorrelationAgent:
    name = "correlation"

    def __init__(self, time_window_minutes: int = 30) -> None:
        self.window = timedelta(minutes=time_window_minutes)

    async def _push_to_neo4j(self, event: Event) -> None:
        try:
            await neo4j_client.upsert_event(
                {
                    "id": str(event.id),
                    "severity": event.severity,
                    "type": event.event_type,
                    "timestamp": event.timestamp.isoformat()
                    if event.timestamp
                    else datetime.now(timezone.utc).isoformat(),
                    "description": event.description,
                    "src_ip": event.src_ip or "unknown",
                    "dst_ip": event.dst_ip or "unknown",
                }
            )
        except Exception as e:
            logger.warning(f"Neo4j upsert failed (continuing): {e}")

    async def _find_related(
        self, session: AsyncSession, event: Event
    ) -> List[Event]:
        """Fetch recent events sharing src_ip or dst_ip."""
        if not event.src_ip and not event.dst_ip:
            return []

        cutoff = datetime.now(timezone.utc) - self.window
        conds = []
        if event.src_ip:
            conds.append(Event.src_ip == event.src_ip)
            conds.append(Event.dst_ip == event.src_ip)
        if event.dst_ip:
            conds.append(Event.dst_ip == event.dst_ip)
            conds.append(Event.src_ip == event.dst_ip)

        from sqlalchemy import or_

        q = await session.execute(
            select(Event).where(
                and_(Event.timestamp >= cutoff, or_(*conds), Event.id != event.id)
            )
        )
        return list(q.scalars().all())

    def _cluster(self, events: List[Event]) -> List[List[Event]]:
        """Weakly-connected components over the IP graph."""
        g = nx.Graph()
        for e in events:
            g.add_node(str(e.id), event=e)
        for i in range(len(events)):
            for j in range(i + 1, len(events)):
                a, b = events[i], events[j]
                shared = {a.src_ip, a.dst_ip} & {b.src_ip, b.dst_ip}
                shared.discard(None)
                if shared:
                    g.add_edge(str(a.id), str(b.id))

        clusters: List[List[Event]] = []
        for comp in nx.connected_components(g):
            clusters.append([g.nodes[n]["event"] for n in comp])
        return clusters

    def _build_chain(self, events: List[Event]) -> Dict:
        """Order events by timestamp to reconstruct the attack chain."""
        ordered = sorted(events, key=lambda e: e.timestamp or datetime.min)
        all_tactics: List[str] = []
        for e in ordered:
            for t in tactics_for(e.event_type):
                if t not in all_tactics:
                    all_tactics.append(t)
        return {
            "chain": [
                {
                    "event_id": str(e.id),
                    "timestamp": e.timestamp.isoformat() if e.timestamp else None,
                    "type": e.event_type,
                    "tactics": tactics_for(e.event_type),
                }
                for e in ordered
            ],
            "tactics": all_tactics,
            "distinct_ips": list(
                {ip for e in ordered for ip in (e.src_ip, e.dst_ip) if ip}
            ),
        }

    async def handle(
        self, event: Event, session: AsyncSession
    ) -> Tuple[Incident, Dict]:
        """Correlate a single event and return its (possibly new) incident."""
        await self._push_to_neo4j(event)

        related = await self._find_related(session, event)
        cluster = [event] + related
        clusters = self._cluster(cluster)
        cluster = next(
            (c for c in clusters if any(e.id == event.id for e in c)), [event]
        )

        chain = self._build_chain(cluster)

        existing_incident_id: Optional[uuid.UUID] = None
        for e in cluster:
            if e.incident_id:
                existing_incident_id = e.incident_id
                break

        if existing_incident_id:
            inc = await session.get(Incident, existing_incident_id)
            if inc is None:
                inc = Incident(id=existing_incident_id, title=f"Incident @ {event.src_ip}")
                session.add(inc)
        else:
            title_ip = event.src_ip or event.dst_ip or "unknown"
            inc = Incident(
                title=f"Suspicious activity involving {title_ip}",
                severity=max(e.severity for e in cluster),
            )
            session.add(inc)
            await session.flush()

        for e in cluster:
            if e.incident_id != inc.id:
                e.incident_id = inc.id

        inc.tactics = chain["tactics"]
        inc.severity = max(e.severity for e in cluster)

        try:
            await neo4j_client.run(
                """
                MERGE (i:Incident {id: $iid})
                  SET i.title = $title, i.severity = $severity
                WITH i
                UNWIND $event_ids AS eid
                MATCH (e:Event {id: eid})
                MERGE (i)-[:CONTAINS]->(e)
                """,
                {
                    "iid": str(inc.id),
                    "title": inc.title,
                    "severity": inc.severity,
                    "event_ids": [str(e.id) for e in cluster],
                },
            )
        except Exception as e:
            logger.warning(f"Neo4j incident-link failed: {e}")

        await session.flush()
        logger.info(
            f"Incident {inc.id}: {len(cluster)} events, "
            f"{len(chain['distinct_ips'])} IPs, tactics={chain['tactics']}"
        )

        # Emit realtime event to dashboard
        try:
            from backend.api.realtime import emit

            await emit(
                "correlate",
                incident_id=str(inc.id),
                n_events=len(cluster),
                tactics=chain["tactics"],
            )
        except Exception:
            pass

        return inc, chain


correlation_agent = CorrelationAgent()