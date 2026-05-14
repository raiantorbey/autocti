"""
Agent 1 — Ingestion & Enrichment.

Pulls raw events (from the /ingest API or the Redis ingest channel),
enriches each event with external threat-intel sources, persists the
enriched event, and forwards it to the correlation agent.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Dict

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.logging import logger
from backend.db.redis_client import (
    CHANNEL_CORRELATE,
    CHANNEL_INGEST,
    get_redis,
)
from backend.integrations import abuseipdb, geoip, shodan_api, virustotal, whois_api
from backend.models.models import Event


# ---- IP enrichment cache (TTL = 5 min) ----
_ENRICH_CACHE: dict[str, tuple[float, dict]] = {}
_ENRICH_TTL = 300.0  # seconds


async def enrich_ip(ip: str) -> Dict[str, Any]:
    """Fan-out enrichment with TTL cache to absorb burst lookups from the sensor."""
    now = time.time()
    cached = _ENRICH_CACHE.get(ip)
    if cached and now - cached[0] < _ENRICH_TTL:
        return cached[1]

    vt, abuse, shod, geo = await asyncio.gather(
        virustotal.lookup_ip(ip),
        abuseipdb.check_ip(ip),
        shodan_api.host_info(ip),
        geoip.lookup(ip),
        return_exceptions=True,
    )

    def _safe(x):
        if isinstance(x, Exception):
            logger.warning(f"Enrichment source errored: {x}")
            return {"error": str(x)}
        return x

    payload = {
        "virustotal": _safe(vt),
        "abuseipdb": _safe(abuse),
        "shodan": _safe(shod),
        "geoip": _safe(geo),
    }
    _ENRICH_CACHE[ip] = (now, payload)

    # Bound cache size
    if len(_ENRICH_CACHE) > 4096:
        for k in sorted(_ENRICH_CACHE, key=lambda k: _ENRICH_CACHE[k][0])[:1024]:
            _ENRICH_CACHE.pop(k, None)
    return payload


class IngestionAgent:
    name = "ingestion"

    async def handle(self, raw: Dict[str, Any], session: AsyncSession) -> Event:
        """Persist an enriched event and return it."""
        enrichment: Dict[str, Any] = {}
        src_ip = raw.get("src_ip")
        dst_ip = raw.get("dst_ip")

        if src_ip:
            enrichment["src"] = await enrich_ip(src_ip)
        if dst_ip:
            enrichment["dst"] = await enrich_ip(dst_ip)

        # WHOIS is slow & best-effort; never let it block the pipeline
        if dst_ip:
            try:
                enrichment["whois"] = await asyncio.wait_for(
                    whois_api.lookup(dst_ip), timeout=3.0
                )
            except asyncio.TimeoutError:
                enrichment["whois"] = {
                    "source": "whois",
                    "query": dst_ip,
                    "error": "timeout",
                }

        # Flatten src enrichment into top-level for risk calc convenience
        if src_ip and "src" in enrichment:
            enrichment["virustotal"] = enrichment["src"].get("virustotal", {})
            enrichment["abuseipdb"] = enrichment["src"].get("abuseipdb", {})
            enrichment["shodan"] = enrichment["src"].get("shodan", {})
            enrichment["geoip"] = enrichment["src"].get("geoip", {})

        event = Event(
            source=raw.get("source", "unknown"),
            event_type=raw.get("event_type", "unknown"),
            src_ip=src_ip,
            dst_ip=dst_ip,
            src_port=raw.get("src_port"),
            dst_port=raw.get("dst_port"),
            protocol=raw.get("protocol"),
            severity=float(raw.get("severity", 0.5)),
            description=raw.get("description", ""),
            raw=raw.get("raw", {}),
            enrichment=enrichment,
        )
        session.add(event)
        await session.flush()  # populate id
        logger.info(f"Event ingested: id={event.id} type={event.event_type}")

        # Notify downstream agent via Redis
        try:
            r = await get_redis()
            await r.publish(CHANNEL_CORRELATE, str(event.id))
        except Exception as e:
            logger.warning(f"Redis publish failed (will proceed inline): {e}")

        # Emit realtime event to dashboard
        try:
            from backend.api.realtime import emit

            await emit(
                "ingest",
                event_id=str(event.id),
                event_type=event.event_type,
                src_ip=event.src_ip,
                dst_ip=event.dst_ip,
            )
        except Exception:
            pass

        return event


ingestion_agent = IngestionAgent()