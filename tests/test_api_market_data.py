from fastapi.testclient import TestClient

from tradesight.api.app import create_app
from tradesight.api.deps import get_market_service
from tradesight.api.settings import ApiSettings
from tradesight.market_data.errors import (
    ProviderError, UnknownAssetError,
)

CANDLE = {"time": 1, "open": 1.0, "high": 2.0, "low": 0.5,
          "close": 1.5, "volume": 10.0}


class FakeService:
    def __init__(self, result=None, exc=None):
        self._result = result
        self._exc = exc

    def get_candles(self, pair, timeframe):
        if self._exc:
            raise self._exc
        return self._result


def client_with(svc):
    settings = ApiSettings(
        _env_file=None, nim_api_key="n", tavily_api_key="t", gemini_api_key="g")
    app = create_app(settings)
    app.dependency_overrides[get_market_service] = lambda: svc
    return TestClient(app)


def test_market_data_success():
    svc = FakeService(result=([CANDLE], "crypto", False))
    resp = client_with(svc).get("/api/market-data?pair=BTC/USDT&timeframe=H1")
    assert resp.status_code == 200
    body = resp.json()
    assert body["asset_class"] == "crypto"
    assert body["delayed"] is False
    assert body["candles"][0]["close"] == 1.5


def test_forex_marked_delayed():
    svc = FakeService(result=([CANDLE], "forex", True))
    resp = client_with(svc).get("/api/market-data?pair=EUR/USD&timeframe=H1")
    assert resp.json()["delayed"] is True


def test_unknown_pair_returns_400():
    svc = FakeService(exc=UnknownAssetError("bad"))
    resp = client_with(svc).get("/api/market-data?pair=FOO/BAR&timeframe=H1")
    assert resp.status_code == 400


def test_provider_error_returns_502():
    svc = FakeService(exc=ProviderError("upstream down"))
    resp = client_with(svc).get("/api/market-data?pair=BTC/USDT&timeframe=H1")
    assert resp.status_code == 502
