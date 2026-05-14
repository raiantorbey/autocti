"""
Agent 5 — Feedback & Learning.

Persists the analyst's verdict on an incident and updates the Risk model
weights accordingly (see backend/ml/risk_model.apply_feedback).
"""
from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.logging import logger
from backend.ml.risk_model import (
    RiskComponents,
    apply_feedback,
    correlation_score,
    exposure_from_enrichment,
)
from backend.models.models import Feedback, Incident, User


class FeedbackAgent:
    name = "feedback"

    async def handle(
        self,
        incident_id: uuid.UUID,
        verdict: str,
        notes: str,
        analyst: User,
        session: AsyncSession,
    ) -> Feedback:
        q = await session.execute(select(Incident).where(Incident.id == incident_id))
        incident: Optional[Incident] = q.scalar_one_or_none()
        if incident is None:
            raise ValueError(f"Incident {incident_id} not found")

        fb = Feedback(
            incident_id=incident.id,
            analyst_id=analyst.id,
            verdict=verdict,
            notes=notes,
        )
        session.add(fb)

        if verdict == "confirmed":
            incident.status = "triaged"
        elif verdict == "false_positive":
            incident.status = "closed"
        else:
            incident.status = "triaged"

        severity = max((e.severity for e in incident.events), default=0.0)
        exposure = 0.0
        for e in incident.events:
            exposure = max(exposure, exposure_from_enrichment(e.enrichment or {}))
        distinct_ips = {
            ip for e in incident.events for ip in (e.src_ip, e.dst_ip) if ip
        }
        corr = correlation_score(len(incident.events), len(distinct_ips))

        await apply_feedback(
            session,
            verdict=verdict,
            contributing=RiskComponents(
                severity=severity, exposure=exposure, correlation=corr
            ),
        )

        await session.flush()
        logger.info(
            f"Feedback recorded: incident={incident.id} verdict={verdict} "
            f"by {analyst.username}"
        )

        # Emit realtime event to dashboard
        try:
            from backend.api.realtime import emit

            await emit(
                "feedback",
                incident_id=str(fb.incident_id),
                verdict=verdict,
            )
        except Exception:
            pass

        return fb


feedback_agent = FeedbackAgent()