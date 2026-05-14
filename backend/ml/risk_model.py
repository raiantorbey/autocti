"""
Risk scoring engine.

    Risk = α·S + β·E + γ·C

where
    S = severity signal (from detection model + event metadata, [0, 1])
    E = exposure / enrichment (reputation, open ports, vulns, geolocation, [0, 1])
    C = correlation/context (graph centrality, event cluster size, [0, 1])

Weights are persisted in Postgres (`risk_weights` row id=1). They are tuned
online by the Feedback agent: when an analyst marks a high-scored incident as a
false positive we lower the component(s) that contributed most; when a low-
scored incident is confirmed, we raise them.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.core.logging import logger
from backend.models.models import RiskWeights


@dataclass
class RiskComponents:
    severity: float
    exposure: float
    correlation: float

    def clamp(self) -> "RiskComponents":
        return RiskComponents(
            severity=max(0.0, min(1.0, self.severity)),
            exposure=max(0.0, min(1.0, self.exposure)),
            correlation=max(0.0, min(1.0, self.correlation)),
        )


async def get_weights(session: AsyncSession) -> Tuple[float, float, float]:
    q = await session.execute(select(RiskWeights).where(RiskWeights.id == 1))
    row = q.scalar_one_or_none()
    if row is None:
        row = RiskWeights(
            id=1,
            alpha=settings.risk_alpha,
            beta=settings.risk_beta,
            gamma=settings.risk_gamma,
        )
        session.add(row)
        await session.flush()
    return row.alpha, row.beta, row.gamma


def compute_risk(comp: RiskComponents, alpha: float, beta: float, gamma: float) -> float:
    c = comp.clamp()
    # Normalise weights so the total output stays in [0, 1]
    total_w = max(alpha + beta + gamma, 1e-6)
    raw = alpha * c.severity + beta * c.exposure + gamma * c.correlation
    return round(raw / total_w, 4)


def exposure_from_enrichment(enrichment: Dict) -> float:
    """Derive E ∈ [0, 1] from enrichment payload."""
    score = 0.0
    # AbuseIPDB confidence 0..100
    abuse = enrichment.get("abuseipdb", {}).get("abuse_confidence_score", 0)
    score += (abuse / 100) * 0.4
    # VirusTotal malicious engines
    vt = enrichment.get("virustotal", {})
    mal = vt.get("malicious", 0)
    score += min(mal / 10, 1.0) * 0.3
    # Shodan: vulns found → higher exposure
    shodan = enrichment.get("shodan", {})
    n_vulns = len(shodan.get("vulns", []))
    n_ports = len(shodan.get("ports", []))
    score += min(n_vulns / 5, 1.0) * 0.2
    score += min(n_ports / 20, 1.0) * 0.1
    return min(score, 1.0)


def correlation_score(n_events: int, n_distinct_ips: int) -> float:
    """C ∈ [0, 1] — larger clusters touching more IPs score higher."""
    # log-ish smooth saturation
    a = min(n_events / 10, 1.0) * 0.6
    b = min(n_distinct_ips / 8, 1.0) * 0.4
    return min(a + b, 1.0)


async def apply_feedback(
    session: AsyncSession,
    verdict: str,
    contributing: RiskComponents,
    lr: float = 0.02,
) -> None:
    """
    Tiny online gradient update to the weights.

    - 'confirmed'       → push weights up in proportion to each component.
    - 'false_positive'  → push weights down.
    - 'dismissed'       → small decay (reviewer wasn't sure).
    """
    q = await session.execute(select(RiskWeights).where(RiskWeights.id == 1))
    row = q.scalar_one_or_none()
    if row is None:
        return

    sign = {"confirmed": +1, "false_positive": -1, "dismissed": -0.25}.get(verdict, 0)
    if sign == 0:
        return

    c = contributing.clamp()
    row.alpha = max(0.0, min(1.0, row.alpha + sign * lr * c.severity))
    row.beta = max(0.0, min(1.0, row.beta + sign * lr * c.exposure))
    row.gamma = max(0.0, min(1.0, row.gamma + sign * lr * c.correlation))

    # renormalise so they sum to ~1 (keeps scale stable)
    total = row.alpha + row.beta + row.gamma
    if total > 0:
        row.alpha, row.beta, row.gamma = row.alpha / total, row.beta / total, row.gamma / total

    await session.flush()
    logger.info(
        f"Weights updated (verdict={verdict}): "
        f"α={row.alpha:.3f} β={row.beta:.3f} γ={row.gamma:.3f}"
    )
