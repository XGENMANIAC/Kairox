from __future__ import annotations

from typing import Callable

import requests

from .errors import ProviderError
from .models import Candle

_KLINES_URL = "https://api.binance.com/api/v3/klines"


class BinanceClient:
    """Binance public klines — free, no API key, real-time crypto OHLCV."""

    def __init__(self, http_get: Callable = requests.get):
        self._get = http_get

    def klines(self, symbol: str, interval: str, limit: int = 200) -> list[Candle]:
        try:
            resp = self._get(
                _KLINES_URL,
                params={"symbol": symbol, "interval": interval, "limit": limit},
                timeout=15,
            )
            resp.raise_for_status()
            rows = resp.json()
        except Exception as exc:  # noqa: BLE001 — normalize all upstream failures
            raise ProviderError(f"Binance request failed: {exc}") from exc

        if not isinstance(rows, list):
            raise ProviderError(f"Binance returned unexpected payload: {rows!r}")
        try:
            return [
                Candle(
                    time=int(r[0]) // 1000,
                    open=float(r[1]), high=float(r[2]), low=float(r[3]),
                    close=float(r[4]), volume=float(r[5]),
                )
                for r in rows
            ]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ProviderError(f"Binance payload parse error: {exc}") from exc
