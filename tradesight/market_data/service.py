from __future__ import annotations

from .cache import CandleCache
from .classify import (
    classify, timeframe_to_interval, to_binance_symbol, to_twelvedata_symbol,
)
from .errors import ForexNotConfiguredError


class MarketDataService:
    """Routes a pair to the right provider, caches per pair+timeframe.

    Returns ``(candles, asset_class, delayed)`` where ``candles`` is a list of
    plain dicts (Lightweight Charts shape) and ``delayed`` is True for forex.
    """

    def __init__(self, cache: CandleCache, binance, twelvedata=None,
                 crypto_ttl: int = 60, forex_ttl: int = 300):
        self._cache = cache
        self._binance = binance
        self._twelvedata = twelvedata
        self._crypto_ttl = crypto_ttl
        self._forex_ttl = forex_ttl

    def get_candles(self, pair: str, timeframe: str) -> tuple[list, str, bool]:
        asset = classify(pair)  # raises UnknownAssetError
        delayed = asset == "forex"
        key = f"candles:{pair}:{timeframe}"

        cached = self._cache.get(key)
        if cached is not None:
            return cached, asset, delayed

        if asset == "crypto":
            symbol = to_binance_symbol(pair)
            interval = timeframe_to_interval(timeframe, "binance")
            candles = self._binance.klines(symbol, interval)
            ttl = self._crypto_ttl
        else:
            if self._twelvedata is None:
                raise ForexNotConfiguredError(
                    "Forex data is not configured (TWELVEDATA_API_KEY missing).")
            symbol = to_twelvedata_symbol(pair)
            interval = timeframe_to_interval(timeframe, "twelvedata")
            candles = self._twelvedata.time_series(symbol, interval)
            ttl = self._forex_ttl

        payload = [c.as_dict() for c in candles]
        self._cache.set(key, payload, ttl)
        return payload, asset, delayed
