from fastapi.testclient import TestClient

from tradesight.api.app import create_app
from tradesight.api.settings import ApiSettings


def make_client():
    settings = ApiSettings(
        _env_file=None, nim_api_key="n", tavily_api_key="t", gemini_api_key="g")
    app = create_app(settings)
    return TestClient(app)


def test_health_ok():
    resp = make_client().get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_security_headers_present():
    resp = make_client().get("/health")
    assert resp.headers["x-frame-options"] == "DENY"
    assert resp.headers["x-content-type-options"] == "nosniff"
