import pytest

from tradesight.market_data.binance import BinanceClient
from tradesight.market_data.errors import ProviderError


class FakeResp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")


def fake_get(payload, status=200):
    captured = {}

    def _get(url, params=None, timeout=None):
        captured["url"] = url
        captured["params"] = params
        return FakeResp(payload, status)

    _get.captured = captured
    return _get


KLINES = [
    [1733400000000, "100.0", "110.0", "95.0", "105.0", "12.5", 0, 0, 0, 0, 0, 0],
    [1733403600000, "105.0", "120.0", "104.0", "118.0", "8.0", 0, 0, 0, 0, 0, 0],
]


def test_klines_parses_candles():
    client = BinanceClient(http_get=fake_get(KLINES))
    candles = client.klines("BTCUSDT", "1h", limit=2)
    assert len(candles) == 2
    assert candles[0].time == 1733400000  # ms -> s
    assert candles[0].open == 100.0
    assert candles[0].close == 105.0
    assert candles[1].high == 120.0


def test_klines_passes_request_params():
    get = fake_get(KLINES)
    BinanceClient(http_get=get).klines("ETHUSDT", "15m", limit=50)
    assert get.captured["params"]["symbol"] == "ETHUSDT"
    assert get.captured["params"]["interval"] == "15m"
    assert get.captured["params"]["limit"] == 50


def test_klines_provider_error_on_http_failure():
    with pytest.raises(ProviderError):
        BinanceClient(http_get=fake_get({"msg": "bad"}, status=400)).klines(
            "BTCUSDT", "1h")


def test_klines_provider_error_on_bad_payload():
    with pytest.raises(ProviderError):
        BinanceClient(http_get=fake_get({"unexpected": "shape"})).klines(
            "BTCUSDT", "1h")
