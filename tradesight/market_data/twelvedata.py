from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

import requests

from .errors import ProviderError
from .models import Candle

_TS_URL = "https://api.twelvedata.com/time_series"


def _to_epoch(s: str) -> int:
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
            return int(dt.timestamp())
        except ValueError:
            continue
    raise ProviderError(f"Twelve Data unparseable datetime: {s!r}")


class TwelveDataClient:
    """Twelve Data time_series — free tier (delayed) forex OHLC."""

    def __init__(self, api_key: str, http_get: Callable = requests.get):
        self._key = api_key
        self._get = http_get

    def time_series(self, symbol: str, interval: str,
                    outputsize: int = 200) -> list[Candle]:
        try:
            resp = self._get(
                _TS_URL,
                params={"symbol": symbol, "interval": interval,
                        "outputsize": outputsize, "apikey": self._key,
                        "format": "JSON"},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:  # noqa: BLE001 — normalize all upstream failures
            raise ProviderError(f"Twelve Data request failed: {exc}") from exc

        if not isinstance(data, dict) or data.get("status") == "error":
            msg = data.get("message") if isinstance(data, dict) else data
            raise ProviderError(f"Twelve Data error: {msg}")
        values = data.get("values")
        if not isinstance(values, list):
            raise ProviderError(f"Twelve Data missing values: {data!r}")
        try:
            candles = [
                Candle(
                    time=_to_epoch(v["datetime"]),
                    open=float(v["open"]), high=float(v["high"]),
                    low=float(v["low"]), close=float(v["close"]),
                    volume=float(v.get("volume") or 0.0),
                )
                for v in values
            ]
        except (KeyError, TypeError, ValueError) as exc:
            raise ProviderError(f"Twelve Data payload parse error: {exc}") from exc
        candles.sort(key=lambda c: c.time)  # API is newest-first; chart needs ascending
        return candles
