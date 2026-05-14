"""VirusTotal v3 API wrapper with mock mode and rate limiting."""
from __future__ import annotations

import asyncio
import hashlib
import time
from typing import Any, Dict

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential_jitter

from backend.core.config import settings
from backend.core.logging import logger

VT_BASE = "https://www.virustotal.com/api/v3"
# Free tier: 4 req/min, 500/day. We self-throttle to be safe.
_MIN_INTERVAL = 16.0  # seconds between calls
_last_call: float = 0.0
_lock = asyncio.Lock()


async def _rate_limit() -> None:
    global _last_call
    async with _lock:
        elapsed = time.monotonic() - _last_call
        if elapsed < _MIN_INTERVAL:
            await asyncio.sleep(_MIN_INTERVAL - elapsed)
        _last_call = time.monotonic()


def _mock_ip(ip: str) -> Dict[str, Any]:
    """Deterministic mock response for offline / no-key mode."""
    h = int(hashlib.md5(ip.encode()).hexdigest(), 16)
    malicious = h % 10  # 0-9
    return {
        "source": "virustotal-mock",
        "ip": ip,
        "malicious": malicious,
        "suspicious": (h >> 4) % 5,
        "harmless": 70 - malicious,
        "reputation": -malicious * 3,
        "country": ["US", "RU", "CN", "DE", "BR"][h % 5],
    }


@retry(stop=stop_after_attempt(3), wait=wait_exponential_jitter(initial=1, max=10))
async def lookup_ip(ip: str) -> Dict[str, Any]:
    """Query VirusTotal for an IP. Falls back to mock mode if no API key."""
    if not settings.virustotal_api_key:
        logger.debug(f"VirusTotal key missing — mock mode for {ip}")
        return _mock_ip(ip)

    await _rate_limit()
    headers = {"x-apikey": settings.virustotal_api_key}
    async with httpx.AsyncClient(timeout=10.0) as c:
        r = await c.get(f"{VT_BASE}/ip_addresses/{ip}", headers=headers)
        if r.status_code == 404:
            return {"source": "virustotal", "ip": ip, "malicious": 0, "unknown": True}
        r.raise_for_status()
        data = r.json().get("data", {}).get("attributes", {})
        stats = data.get("last_analysis_stats", {})
        return {
            "source": "virustotal",
            "ip": ip,
            "malicious": stats.get("malicious", 0),
            "suspicious": stats.get("suspicious", 0),
            "harmless": stats.get("harmless", 0),
            "reputation": data.get("reputation", 0),
            "country": data.get("country", ""),
        }
