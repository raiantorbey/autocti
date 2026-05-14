"""AbuseIPDB integration with mock mode."""
from __future__ import annotations

import hashlib
from typing import Any, Dict

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential_jitter

from backend.core.config import settings
from backend.core.logging import logger

BASE = "https://api.abuseipdb.com/api/v2"


def _mock(ip: str) -> Dict[str, Any]:
    h = int(hashlib.md5(ip.encode()).hexdigest(), 16)
    return {
        "source": "abuseipdb-mock",
        "ip": ip,
        "abuse_confidence_score": h % 100,
        "total_reports": h % 500,
        "country_code": ["US", "CN", "RU", "IN", "BR"][h % 5],
        "isp": "MockISP",
        "is_tor": (h % 13) == 0,
    }


@retry(stop=stop_after_attempt(3), wait=wait_exponential_jitter(initial=1, max=8))
async def check_ip(ip: str, max_age_days: int = 90) -> Dict[str, Any]:
    if not settings.abuseipdb_api_key:
        logger.debug(f"AbuseIPDB key missing — mock mode for {ip}")
        return _mock(ip)

    headers = {"Key": settings.abuseipdb_api_key, "Accept": "application/json"}
    params = {"ipAddress": ip, "maxAgeInDays": max_age_days}
    async with httpx.AsyncClient(timeout=10.0) as c:
        r = await c.get(f"{BASE}/check", headers=headers, params=params)
        r.raise_for_status()
        d = r.json().get("data", {})
        return {
            "source": "abuseipdb",
            "ip": ip,
            "abuse_confidence_score": d.get("abuseConfidenceScore", 0),
            "total_reports": d.get("totalReports", 0),
            "country_code": d.get("countryCode", ""),
            "isp": d.get("isp", ""),
            "is_tor": d.get("isTor", False),
        }
