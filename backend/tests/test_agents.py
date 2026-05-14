"""Tests for agent helpers that don't require live services."""
import pytest

from backend.agents.correlation_agent import CorrelationAgent, tactics_for
from backend.integrations import abuseipdb, geoip, shodan_api, virustotal, whois_api


def test_tactics_mapping():
    assert "Reconnaissance" in tactics_for("port_scan")
    assert "Command and Control" in tactics_for("c2")
    assert tactics_for("unknown_type") == []


@pytest.mark.asyncio
async def test_mock_integrations_offline():
    """With no API keys set, every integration returns a dict (mock mode)."""
    ip = "8.8.8.8"
    vt = await virustotal.lookup_ip(ip)
    ab = await abuseipdb.check_ip(ip)
    sh = await shodan_api.host_info(ip)
    geo = await geoip.lookup(ip)
    w = await whois_api.lookup(ip)

    for r in (vt, ab, sh, geo, w):
        assert isinstance(r, dict)
        assert "source" in r


def test_cluster_grouping_finds_two_components():
    """Two disjoint pairs of events should yield two clusters."""
    from types import SimpleNamespace

    events = [
        SimpleNamespace(id="1", src_ip="1.1.1.1", dst_ip="2.2.2.2"),
        SimpleNamespace(id="2", src_ip="1.1.1.1", dst_ip="3.3.3.3"),
        SimpleNamespace(id="3", src_ip="9.9.9.9", dst_ip="8.8.8.8"),
        SimpleNamespace(id="4", src_ip="8.8.8.8", dst_ip="7.7.7.7"),
    ]
    agent = CorrelationAgent()
    clusters = agent._cluster(events)
    assert len(clusters) == 2
    sizes = sorted(len(c) for c in clusters)
    assert sizes == [2, 2]
