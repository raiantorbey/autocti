"""Smoke tests that instantiate the FastAPI app (no external services needed)."""
from fastapi.testclient import TestClient


def test_app_starts_and_health():
    # Import lazily so test collection doesn't fail if optional deps are missing
    from backend.main import app

    with TestClient(app) as client:
        r = client.get("/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert body["app"] == "AutoCTI"


def test_auth_required_on_incidents():
    from backend.main import app

    with TestClient(app) as client:
        r = client.get("/api/incidents")
        # Missing token → 401
        assert r.status_code == 401


def test_login_wrong_password():
    from backend.main import app

    with TestClient(app) as client:
        r = client.post(
            "/api/auth/login",
            data={"username": "nobody", "password": "wrong"},
        )
        assert r.status_code == 401
