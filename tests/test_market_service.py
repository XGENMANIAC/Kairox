import pytest

from tradesight.market_data.cache import CandleCache
from tradesight.market_data.models import Candle
from tradesight.market_data.service import MarketDataService
from tradesight.market_data.errors import (
    ForexNotConfiguredError, UnknownAssetError,
)


class FakeBinance:
    def __init__(self):
        self.calls = []

    def klines(self, symbol, interval, limit=200):
        self.calls.append((symbol, interval))
        return [Candle(1, 1, 2, 0.5, 1.5, 10)]


class FakeTwelve:
    def __init__(self):
        self.calls = []

    def time_series(self, symbol, interval, outputsize=200):
        self.calls.append((symbol, interval))
        return [Candle(2, 1, 2, 0.5, 1.5, 0)]


def svc(twelve=None):
    return MarketDataService(CandleCache(), FakeBinance(), twelvedata=twelve)


def test_crypto_routes_to_binance():
    s = svc()
    candles, asset, delayed = s.get_candles("BTC/USDT", "H1")
    assert asset == "crypto"
    assert delayed is False
    assert candles == [{"time": 1, "open": 1.0, "high": 2.0,
                        "low": 0.5, "close": 1.5, "volume": 10.0}]


def test_forex_routes_to_twelvedata_and_marks_delayed():
    s = svc(twelve=FakeTwelve())
    candles, asset, delayed = s.get_candles("EUR/USD", "H1")
    assert asset == "forex"
    assert delayed is True
    assert candles[0]["time"] == 2


def test_forex_without_key_raises():
    with pytest.raises(ForexNotConfiguredError):
        svc(twelve=None).get_candles("EUR/USD", "H1")


def test_unknown_pair_raises():
    with pytest.raises(UnknownAssetError):
        svc().get_candles("FOO/BAR", "H1")


def test_second_call_served_from_cache():
    binance = FakeBinance()
    s = MarketDataService(CandleCache(), binance)
    s.get_candles("BTC/USDT", "H1")
    s.get_candles("BTC/USDT", "H1")
    assert len(binance.calls) == 1  # provider hit once; second served from cache
