"""WHOIS lookup. No API key required (uses python-whois)."""
from __future__ import annotations

import asyncio
import hashlib
from typing import Any, Dict

from backend.core.logging import logger


def _mock(query: str) -> Dict[str, Any]:
    h = int(hashlib.md5(query.encode()).hexdigest(), 16)
    return {
        "source": "whois-mock",
        "query": query,
        "registrar": ["GoDaddy", "Namecheap", "Google", "OVH"][h % 4],
        "country": ["US", "FR", "DE", "NL"][h % 4],
        "creation_date": "2015-04-12",
        "expiration_date": "2026-04-12",
    }


async def lookup(query: str) -> Dict[str, Any]:
    """query may be a domain or IP."""

    def _call() -> Dict[str, Any]:
        try:
            import whois  # python-whois

            w = whois.whois(query)
            if not w or not w.get("domain_name"):
                return _mock(query)
            return {
                "source": "whois",
                "query": query,
                "registrar": str(w.get("registrar") or ""),
                "country": str(w.get("country") or ""),
                "creation_date": str(w.get("creation_date") or ""),
                "expiration_date": str(w.get("expiration_date") or ""),
            }
        except Exception as e:
            logger.debug(f"WHOIS failed for {query}: {e} — mock")
            return _mock(query)

    return await asyncio.to_thread(_call)
