import pytest

from tradesight.market_data.twelvedata import TwelveDataClient
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
        captured["params"] = params
        return FakeResp(payload, status)

    _get.captured = captured
    return _get


# Twelve Data returns newest-first values.
TS_OK = {
    "status": "ok",
    "values": [
        {"datetime": "2026-06-05 11:00:00", "open": "1.10", "high": "1.12",
         "low": "1.09", "close": "1.11", "volume": "0"},
        {"datetime": "2026-06-05 10:00:00", "open": "1.08", "high": "1.105",
         "low": "1.07", "close": "1.10", "volume": "0"},
    ],
}


def test_time_series_parses_and_sorts_ascending():
    client = TwelveDataClient("key", http_get=fake_get(TS_OK))
    candles = client.time_series("EUR/USD", "1h", outputsize=2)
    assert len(candles) == 2
    # oldest first after sort
    assert candles[0].close == 1.10
    assert candles[1].close == 1.11
    assert candles[0].time < candles[1].time


def test_time_series_sends_apikey_and_params():
    get = fake_get(TS_OK)
    TwelveDataClient("secret", http_get=get).time_series("EUR/USD", "1h")
    assert get.captured["params"]["apikey"] == "secret"
    assert get.captured["params"]["symbol"] == "EUR/USD"
    assert get.captured["params"]["interval"] == "1h"


def test_time_series_error_status_raises():
    bad = {"status": "error", "message": "invalid symbol"}
    with pytest.raises(ProviderError):
        TwelveDataClient("k", http_get=fake_get(bad)).time_series("X/Y", "1h")


def test_time_series_http_failure_raises():
    with pytest.raises(ProviderError):
        TwelveDataClient("k", http_get=fake_get({}, status=429)).time_series(
            "EUR/USD", "1h")
