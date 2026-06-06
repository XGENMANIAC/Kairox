from __future__ import annotations

import json
import time
from typing import Callable, Optional


class CandleCache:
    """Per pair+timeframe candle cache, shared across all callers.

    Uses Upstash/Redis when ``redis_url`` is provided; otherwise an in-memory
    TTL dict (no infra needed locally / in tests). ``now`` is injectable so
    expiry is testable without sleeping.
    """

    def __init__(self, redis_url: Optional[str] = None,
                 now: Callable[[], float] = time.time):
        self._now = now
        self._redis = None
        if redis_url:
            import redis  # imported lazily so the dep is optional
            self._redis = redis.from_url(redis_url)
        self._mem: dict[str, tuple[float, list]] = {}

    def get(self, key: str) -> Optional[list]:
        if self._redis is not None:
            raw = self._redis.get(key)
            return json.loads(raw) if raw else None
        item = self._mem.get(key)
        if item is None:
            return None
        expires, value = item
        if self._now() >= expires:
            self._mem.pop(key, None)
            return None
        return value

    def set(self, key: str, value: list, ttl: int) -> None:
        if self._redis is not None:
            self._redis.set(key, json.dumps(value), ex=ttl)
            return
        self._mem[key] = (self._now() + ttl, value)
