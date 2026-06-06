import base64

from fastapi.testclient import TestClient

from tradesight.analyzer import Analysis
from tradesight.api.app import create_app
from tradesight.api.deps import get_analyzer, get_news
from tradesight.api.settings import ApiSettings

PNG = b"\x89PNG\r\n\x1a\n" + b"body"


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


class FakeAnalyzer:
    def __init__(self):
        self.kwargs = None

    def analyze(self, image_b64, session, news_report=None,
                on_stage=None, news_provider=None):
        self.kwargs = {"news_report": news_report, "news_provider": news_provider}
        return Analysis(pair="EUR/USD", signal="BUY", confidence=70,
                        chart_detected=True)


class FakeNews:
    def report(self, pair):
        return ({"summary": "s"}, True)

    def report_or_none(self, pair):
        return {"summary": "s"}


def client_with(analyzer, news):
    settings = ApiSettings(
        _env_file=None, nim_api_key="n", tavily_api_key="t", gemini_api_key="g")
    app = create_app(settings)
    app.dependency_overrides[get_analyzer] = lambda: analyzer
    app.dependency_overrides[get_news] = lambda: news
    return TestClient(app)


def test_analyse_returns_analysis_with_disclaimer():
    c = client_with(FakeAnalyzer(), FakeNews())
    resp = c.post("/api/analyse", json={"image": b64(PNG)})
    assert resp.status_code == 200
    body = resp.json()
    assert body["pair"] == "EUR/USD"
    assert body["signal"] == "BUY"
    assert "not financial advice" in body["disclaimer"].lower()


def test_analyse_uses_news_provider_when_no_pair():
    fa = FakeAnalyzer()
    c = client_with(fa, FakeNews())
    c.post("/api/analyse", json={"image": b64(PNG)})
    assert fa.kwargs["news_provider"] is not None
    assert fa.kwargs["news_report"] is None


def test_analyse_fetches_news_up_front_when_pair_given():
    fa = FakeAnalyzer()
    c = client_with(fa, FakeNews())
    c.post("/api/analyse", json={"image": b64(PNG), "pair": "EUR/USD"})
    assert fa.kwargs["news_report"] == {"summary": "s"}


def test_analyse_rejects_non_png():
    c = client_with(FakeAnalyzer(), FakeNews())
    resp = c.post("/api/analyse", json={"image": b64(b"notpng")})
    assert resp.status_code == 422
