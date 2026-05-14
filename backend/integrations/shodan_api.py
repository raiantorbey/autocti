"""Shodan host lookup with mock fallback."""
from __future__ import annotations

import asyncio
import hashlib
from typing import Any, Dict

from backend.core.config import settings
from backend.core.logging import logger


def _mock(ip: str) -> Dict[str, Any]:
    h = int(hashlib.md5(ip.encode()).hexdigest(), 16)
    ports = [22, 80, 443, 21, 3306, 3389, 8080]
    open_ports = [p for i, p in enumerate(ports) if (h >> i) & 1]
    return {
        "source": "shodan-mock",
        "ip": ip,
        "ports": open_ports,
        "vulns": [f"CVE-2023-{1000 + (h % 9000)}"] if h % 4 == 0 else [],
        "os": ["Linux", "Windows", "FreeBSD"][h % 3],
        "org": "MockOrg Ltd",
        "hostnames": [f"host-{h % 1000}.example.com"],
    }


async def host_info(ip: str) -> Dict[str, Any]:
    if not settings.shodan_api_key:
        logger.debug(f"Shodan key missing — mock mode for {ip}")
        return _mock(ip)

    # Shodan's python lib is synchronous — run in threadpool
    def _call() -> Dict[str, Any]:
        import shodan

        api = shodan.Shodan(settings.shodan_api_key)
        try:
            h = api.host(ip)
        except shodan.APIError as e:
            logger.warning(f"Shodan APIError for {ip}: {e}")
            return {"source": "shodan", "ip": ip, "error": str(e)}
        return {
            "source": "shodan",
            "ip": ip,
            "ports": h.get("ports", []),
            "vulns": list(h.get("vulns", []) or []),
            "os": h.get("os"),
            "org": h.get("org"),
            "hostnames": h.get("hostnames", []),
        }

    return await asyncio.to_thread(_call)
