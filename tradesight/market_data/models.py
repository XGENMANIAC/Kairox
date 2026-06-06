from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Candle:
    """One OHLCV bar. ``time`` is a UNIX epoch in seconds (Lightweight Charts)."""
    time: int
    open: float
    high: float
    low: float
    close: float
    volume: float

    def as_dict(self) -> dict:
        return {
            "time": int(self.time),
            "open": float(self.open),
            "high": float(self.high),
            "low": float(self.low),
            "close": float(self.close),
            "volume": float(self.volume),
        }
