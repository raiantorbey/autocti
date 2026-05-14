"""GeoIP enrichment. Uses ipinfo.io; falls back to mock."""
from __future__ import annotations

import hashlib
from typing import Any, Dict

import httpx

from backend.core.config import settings
from backend.core.logging import logger


def _mock(ip: str) -> Dict[str, Any]:
    h = int(hashlib.md5(ip.encode()).hexdigest(), 16)
    countries = ["US", "FR", "DE", "JP", "BR", "CN", "RU", "IN"]
    cities = ["NY", "Paris", "Berlin", "Tokyo", "SP", "Beijing", "Moscow", "Mumbai"]
    idx = h % len(countries)
    return {
        "source": "geoip-mock",
        "ip": ip,
        "country": countries[idx],
        "city": cities[idx],
        "loc": f"{(h % 180) - 90},{(h % 360) - 180}",
        "org": f"AS{h % 65000} MockNet",
    }


async def lookup(ip: str) -> Dict[str, Any]:
    if not settings.geoip_api_key:
        logger.debug(f"GeoIP key missing — mock mode for {ip}")
        return _mock(ip)

    url = f"https://ipinfo.io/{ip}?token={settings.geoip_api_key}"
    try:
        async with httpx.AsyncClient(timeout=5.0) as c:
            r = await c.get(url)
            r.raise_for_status()
            d = r.json()
            return {
                "source": "geoip",
                "ip": ip,
                "country": d.get("country", ""),
                "city": d.get("city", ""),
                "loc": d.get("loc", ""),
                "org": d.get("org", ""),
            }
    except Exception as e:
        logger.warning(f"GeoIP lookup failed for {ip}: {e} — using mock")
        return _mock(ip)
