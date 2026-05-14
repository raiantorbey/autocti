"""Unit tests for the risk scoring primitives."""
import pytest

from backend.ml.risk_model import (
    RiskComponents,
    compute_risk,
    correlation_score,
    exposure_from_enrichment,
)


def test_compute_risk_all_zero():
    r = compute_risk(RiskComponents(0, 0, 0), 0.5, 0.3, 0.2)
    assert r == 0.0


def test_compute_risk_all_one():
    r = compute_risk(RiskComponents(1, 1, 1), 0.5, 0.3, 0.2)
    assert r == 1.0


def test_compute_risk_clamps():
    r = compute_risk(RiskComponents(2, -1, 0.5), 0.5, 0.3, 0.2)
    assert 0 <= r <= 1


def test_compute_risk_weight_shape():
    low = compute_risk(RiskComponents(0.2, 0.0, 0.0), 1, 0, 0)
    high = compute_risk(RiskComponents(0.8, 0.0, 0.0), 1, 0, 0)
    assert high > low


def test_exposure_from_enrichment_scales():
    low = exposure_from_enrichment(
        {"abuseipdb": {"abuse_confidence_score": 10}, "virustotal": {"malicious": 0}}
    )
    high = exposure_from_enrichment(
        {
            "abuseipdb": {"abuse_confidence_score": 99},
            "virustotal": {"malicious": 8},
            "shodan": {"vulns": ["CVE-1", "CVE-2", "CVE-3"], "ports": list(range(15))},
        }
    )
    assert 0.0 <= low <= 1.0 and 0.0 <= high <= 1.0
    assert high > low


def test_correlation_score_monotone():
    a = correlation_score(1, 1)
    b = correlation_score(5, 3)
    c = correlation_score(20, 10)
    assert a <= b <= c


@pytest.mark.parametrize("alpha,beta,gamma", [(1, 0, 0), (0, 1, 0), (0, 0, 1)])
def test_single_component_weight(alpha, beta, gamma):
    r = compute_risk(RiskComponents(1, 1, 1), alpha, beta, gamma)
    assert r == pytest.approx(1.0)
