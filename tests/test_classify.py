import pytest

from tradesight.market_data.classify import (
    classify, split_pair, to_binance_symbol, to_twelvedata_symbol,
    timeframe_to_interval,
)
from tradesight.market_data.errors import (
    UnknownAssetError, UnsupportedTimeframeError,
)


def test_split_pair():
    assert split_pair("EUR/USD") == ("EUR", "USD")
    assert split_pair("btc/usdt") == ("BTC", "USDT")


def test_classify_crypto_by_quote():
    assert classify("BTC/USDT") == "crypto"
    assert classify("ETH/USDC") == "crypto"


def test_classify_crypto_by_base():
    assert classify("SOL/USD") == "crypto"


def test_classify_forex():
    assert classify("EUR/USD") == "forex"
    assert classify("GBP/JPY") == "forex"


def test_classify_unknown_raises():
    with pytest.raises(UnknownAssetError):
        classify("FOO/BAR")


def test_to_binance_symbol():
    assert to_binance_symbol("BTC/USDT") == "BTCUSDT"


def test_to_twelvedata_symbol():
    assert to_twelvedata_symbol("EUR/USD") == "EUR/USD"


def test_timeframe_to_interval_binance():
    assert timeframe_to_interval("H1", "binance") == "1h"
    assert timeframe_to_interval("M15", "binance") == "15m"
    assert timeframe_to_interval("D1", "binance") == "1d"


def test_timeframe_to_interval_twelvedata():
    assert timeframe_to_interval("H1", "twelvedata") == "1h"
    assert timeframe_to_interval("M15", "twelvedata") == "15min"
    assert timeframe_to_interval("D1", "twelvedata") == "1day"


def test_timeframe_unsupported_raises():
    with pytest.raises(UnsupportedTimeframeError):
        timeframe_to_interval("H3", "binance")
