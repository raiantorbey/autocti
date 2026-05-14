"""
Incidents + events API.

POST   /api/events/ingest        → run the full agent pipeline on a new event
GET    /api/incidents            → lightweight list, sorted by risk desc
GET    /api/incidents/{id}       → full detail incl. events
GET    /api/incidents/{id}/similar → vector-store similar incidents
GET    /api/events               → paginated, filterable event log
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.agents.correlation_agent import correlation_agent
from backend.agents.explanation_agent import explanation_agent
from backend.agents.ingestion_agent import ingestion_agent
from backend.agents.risk_agent import risk_agent
from backend.core.security import ROLE_ANALYST, ROLE_READONLY, require_roles
from backend.db.chroma_client import vector_store
from backend.db.postgres import get_session
from backend.ml.embeddings import embed, incident_text
from backend.models.models import Event, Incident
from backend.schemas.schemas import EventIn, EventOut, IncidentDetail

router = APIRouter(prefix="/api", tags=["incidents"])


# ---------------- ingest ----------------
@router.post(
    "/events/ingest",
    response_model=IncidentDetail,
    dependencies=[Depends(require_roles(*ROLE_ANALYST))],
)
async def ingest_event(payload: EventIn, session: AsyncSession = Depends(get_session)):
    event = await ingestion_agent.handle(payload.model_dump(), session)
    incident, chain = await correlation_agent.handle(event, session)
    q = await session.execute(
        select(Incident)
        .options(selectinload(Incident.events))
        .where(Incident.id == incident.id)
    )
    incident = q.scalar_one()
    await risk_agent.handle(incident, chain, session)
    await explanation_agent.handle(incident, chain, session)
    q = await session.execute(
        select(Incident)
        .options(selectinload(Incident.events))
        .where(Incident.id == incident.id)
    )
    return q.scalar_one()


# ---------------- incidents list ----------------
@router.get(
    "/incidents",
    dependencies=[Depends(require_roles(*ROLE_READONLY))],
)
async def list_incidents(
    limit: int = Query(50, ge=1, le=500),
    status_filter: Optional[str] = Query(None, alias="status"),
    session: AsyncSession = Depends(get_session),
):
    cols = (
        Incident.id, Incident.title, Incident.status, Incident.severity,
        Incident.risk_score, Incident.tactics, Incident.created_at, Incident.updated_at,
    )
    stmt = (
        select(*cols)
        .order_by(desc(Incident.risk_score), desc(Incident.created_at))
        .limit(limit)
    )
    if status_filter:
        stmt = stmt.where(Incident.status == status_filter)
    rows = (await session.execute(stmt)).all()
    return [
        {
            "id": str(r.id), "title": r.title, "status": r.status,
            "severity": r.severity, "risk_score": r.risk_score,
            "tactics": r.tactics or [],
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        }
        for r in rows
    ]


# ---------------- incident detail ----------------
@router.get(
    "/incidents/{incident_id}",
    response_model=IncidentDetail,
    dependencies=[Depends(require_roles(*ROLE_READONLY))],
)
async def incident_detail(incident_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    q = await session.execute(
        select(Incident)
        .options(selectinload(Incident.events))
        .where(Incident.id == incident_id)
    )
    inc = q.scalar_one_or_none()
    if inc is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    return inc


# ---------------- similar incidents ----------------
@router.get(
    "/incidents/{incident_id}/similar",
    dependencies=[Depends(require_roles(*ROLE_READONLY))],
)
async def similar_incidents(
    incident_id: uuid.UUID,
    k: int = Query(5, ge=1, le=20),
    session: AsyncSession = Depends(get_session),
):
    q = await session.execute(
        select(Incident)
        .options(selectinload(Incident.events))
        .where(Incident.id == incident_id)
    )
    inc = q.scalar_one_or_none()
    if inc is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    text = incident_text({
        "title": inc.title,
        "events": [
            {
                "event_type": e.event_type, "src_ip": e.src_ip, "dst_ip": e.dst_ip,
                "severity": e.severity, "description": e.description,
            }
            for e in inc.events
        ],
    })
    if not text:
        return []
    return vector_store.query(embed(text), n_results=k)


# ====================================================================
# EVENTS API — paginated, filterable, sortable
# ====================================================================
@router.get(
    "/events",
    dependencies=[Depends(require_roles(*ROLE_READONLY))],
)
async def list_events(
    # pagination
    limit: int = Query(50, ge=1, le=500, description="Max rows to return"),
    offset: int = Query(0, ge=0, description="Rows to skip"),
    # filtering
    severity_min: Optional[float] = Query(None, ge=0.0, le=1.0),
    severity_max: Optional[float] = Query(None, ge=0.0, le=1.0),
    src_ip: Optional[str] = Query(None, description="Source IP exact match"),
    dst_ip: Optional[str] = Query(None, description="Destination IP exact match"),
    event_type: Optional[str] = Query(None),
    source: Optional[str] = Query(None, description="Sensor/ingest source"),
    since: Optional[datetime] = Query(None, description="ISO 8601, events after this time"),
    until: Optional[datetime] = Query(None, description="ISO 8601, events before this time"),
    q: Optional[str] = Query(None, description="Free-text search across description/IPs/type"),
    # sorting
    sort: str = Query("timestamp", regex="^(timestamp|severity)$"),
    order: str = Query("desc", regex="^(asc|desc)$"),
    session: AsyncSession = Depends(get_session),
):
    """
    Paginated, filterable, sortable event log.

    Returns a payload of the form:
        {
            "total":  <int>,         # total rows matching filters
            "limit":  <int>,
            "offset": <int>,
            "items":  [ ...events... ]
        }
    """
    conds = []
    if severity_min is not None:
        conds.append(Event.severity >= severity_min)
    if severity_max is not None:
        conds.append(Event.severity <= severity_max)
    if src_ip:
        conds.append(Event.src_ip == src_ip)
    if dst_ip:
        conds.append(Event.dst_ip == dst_ip)
    if event_type:
        conds.append(Event.event_type == event_type)
    if source:
        conds.append(Event.source == source)
    if since:
        conds.append(Event.timestamp >= since)
    if until:
        conds.append(Event.timestamp <= until)
    if q:
        like = f"%{q}%"
        conds.append(or_(
            Event.description.ilike(like),
            Event.src_ip.ilike(like),
            Event.dst_ip.ilike(like),
            Event.event_type.ilike(like),
        ))

    # total count
    count_stmt = select(func.count(Event.id))
    if conds:
        count_stmt = count_stmt.where(and_(*conds))
    total = (await session.execute(count_stmt)).scalar_one()

    # rows
    sort_col = Event.timestamp if sort == "timestamp" else Event.severity
    sort_expr = desc(sort_col) if order == "desc" else sort_col

    stmt = (
        select(
            Event.id, Event.source, Event.event_type, Event.src_ip, Event.dst_ip,
            Event.src_port, Event.dst_port, Event.protocol,
            Event.severity, Event.description, Event.timestamp,
            Event.incident_id,
        )
        .order_by(sort_expr)
        .limit(limit)
        .offset(offset)
    )
    if conds:
        stmt = stmt.where(and_(*conds))

    rows = (await session.execute(stmt)).all()
    items = [
        {
            "id": str(r.id),
            "source": r.source,
            "event_type": r.event_type,
            "src_ip": r.src_ip,
            "dst_ip": r.dst_ip,
            "src_port": r.src_port,
            "dst_port": r.dst_port,
            "protocol": r.protocol,
            "severity": r.severity,
            "description": r.description,
            "timestamp": r.timestamp.isoformat() if r.timestamp else None,
            "incident_id": str(r.incident_id) if r.incident_id else None,
        }
        for r in rows
    ]

    return {"total": total, "limit": limit, "offset": offset, "items": items}