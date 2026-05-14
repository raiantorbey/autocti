"""
Agent 3 — Prioritization & Risk Scoring.

Uses the Risk = αS + βE + γC model from backend/ml/risk_model.py.
"""
from __future__ import annotations

from typing import Dict

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.logging import logger
from backend.ml.risk_model import (
    RiskComponents,
    compute_risk,
    correlation_score,
    exposure_from_enrichment,
    get_weights,
)
from backend.models.models import Incident


class RiskAgent:
    name = "risk"

    async def handle(
        self,
        incident: Incident,
        chain: Dict,
        session: AsyncSession,
    ) -> float:
        severity = max((e.severity for e in incident.events), default=0.0)

        exposure = 0.0
        for e in incident.events:
            exposure = max(exposure, exposure_from_enrichment(e.enrichment or {}))

        c = correlation_score(
            n_events=len(incident.events),
            n_distinct_ips=len(chain.get("distinct_ips", [])),
        )

        comp = RiskComponents(severity=severity, exposure=exposure, correlation=c)
        alpha, beta, gamma = await get_weights(session)
        risk = compute_risk(comp, alpha, beta, gamma)

        incident.risk_score = risk
        incident.recommended_actions = incident.recommended_actions or []
        await session.flush()

        logger.info(
            f"Incident {incident.id}: S={severity:.2f} E={exposure:.2f} "
            f"C={c:.2f} → risk={risk:.3f} (α={alpha:.2f} β={beta:.2f} γ={gamma:.2f})"
        )

        # Emit realtime event to dashboard
        try:
            from backend.api.realtime import emit

            await emit(
                "score",
                incident_id=str(incident.id),
                risk=risk,
                severity=severity,
                exposure=exposure,
                correlation=c,
                alpha=alpha,
                beta=beta,
                gamma=gamma,
            )
        except Exception:
            pass

        return risk


risk_agent = RiskAgent()