# TradeSight Backend Vertical Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up a FastAPI backend inside the existing `tradesight/` package exposing `POST /api/analyse` (Gemini vision + Kimi reasoning + llama news) and `GET /api/market-data` (Binance crypto / Twelve Data forex, cached per pair+timeframe), with no auth yet.

**Architecture:** Reuse the proven `analyzer`/`news`/`context`/`prompts`/`jsonutil`/`config` modules unchanged except one well-bounded analyzer hook. Add a new `tradesight/market_data/` package and a `tradesight/api/` FastAPI app. `ApiSettings` (pydantic-settings) validates env fail-fast and produces a core `Config` for the reused logic. Dependency injection via `request.app.state` so tests override with fakes.

**Tech Stack:** FastAPI, uvicorn, pydantic-settings, slowapi, redis (optional), requests, openai (existing), pytest.

**Spec:** `docs/superpowers/specs/2026-06-06-tradesight-backend-vertical-design.md`

**Conventions in this codebase:** tests are plain `pytest` functions (no classes) under `tests/test_*.py`; fakes are hand-rolled (see `tests/test_analyzer.py`'s `FakeClient`); `from __future__ import annotations` at the top of modules; `# noqa: BLE001` on intentional broad excepts.

---

### Task 1: Dependencies and environment

**Files:**
- Modify: `requirements.txt`
- Modify: `.env.example`

- [ ] **Step 1: Add backend dependencies**

Append to `requirements.txt`:

```
fastapi>=0.110
uvicorn[standard]>=0.29
pydantic-settings>=2.0
redis>=5.0
slowapi>=0.1.9
httpx>=0.27
```

- [ ] **Step 2: Install**

Run: `pip install -r requirements.txt`
Expected: installs without error.

- [ ] **Step 3: Update `.env.example`**

Ensure `.env.example` contains (add any missing keys):

```
# --- LLM providers ---
NIM_API_KEY=
TAVILY_API_KEY=
GEMINI_API_KEY=
VISION_MODEL=gemini-2.5-flash
REASONING_MODEL=moonshotai/kimi-k2.6
NEWS_MODEL=meta/llama-3.3-70b-instruct
# --- Market data ---
TWELVEDATA_API_KEY=
# --- Infra ---
REDIS_URL=
FRONTEND_ORIGIN=http://localhost:5173
ANALYSE_RATE_LIMIT=10/minute
```

- [ ] **Step 4: Commit**

```bash
git add requirements.txt .env.example
git commit -m "chore: add FastAPI backend dependencies and env template"
```

---

### Task 2: Market-data models and errors

**Files:**
- Create: `tradesight/market_data/__init__.py`
- Create: `tradesight/market_data/models.py`
- Create: `tradesight/market_data/errors.py`
- Test: `tests/test_market_models.py`

- [ ] **Step 1: Write the failing test**

`tests/test_market_models.py`:

```python
from tradesight.market_data.models import Candle


def test_candle_as_dict_has_lightweight_charts_shape():
    c = Candle(time=1733400000, open=1.0, high=2.0, low=0.5, close=1.5, volume=10.0)
    assert c.as_dict() == {
        "time": 1733400000, "open": 1.0, "high": 2.0,
        "low": 0.5, "close": 1.5, "volume": 10.0,
    }


def test_candle_time_is_int_epoch_seconds():
    c = Candle(time=1733400000, open=1, high=1, low=1, close=1, volume=0)
    assert isinstance(c.as_dict()["time"], int)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_market_models.py -v`
Expected: FAIL with `ModuleNotFoundError: tradesight.market_data`.

- [ ] **Step 3: Create the package and modules**

`tradesight/market_data/__init__.py`:

```python
```

(empty file)

`tradesight/market_data/models.py`:

```python
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
```

`tradesight/market_data/errors.py`:

```python
from __future__ import annotations


class UnknownAssetError(ValueError):
    """Pair cannot be classified as crypto or forex."""


class UnsupportedTimeframeError(ValueError):
    """Timeframe is not in the supported set."""


class ForexNotConfiguredError(ValueError):
    """Forex requested but no Twelve Data API key is configured."""


class ProviderError(Exception):
    """An upstream market-data provider failed or returned a bad payload."""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_market_models.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add tradesight/market_data/__init__.py tradesight/market_data/models.py tradesight/market_data/errors.py tests/test_market_models.py
git commit -m "feat: market-data Candle model and error types"
```

---

### Task 3: Pair classification and symbol/timeframe mapping

**Files:**
- Create: `tradesight/market_data/classify.py`
- Test: `tests/test_classify.py`

- [ ] **Step 1: Write the failing test**

`tests/test_classify.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_classify.py -v`
Expected: FAIL with `ModuleNotFoundError` / import error.

- [ ] **Step 3: Write the implementation**

`tradesight/market_data/classify.py`:

```python
from __future__ import annotations

from .errors import UnknownAssetError, UnsupportedTimeframeError

# Quotes that mark a pair as crypto regardless of the base.
CRYPTO_QUOTES = {"USDT", "USDC", "BUSD", "DAI", "TUSD", "BTC", "ETH", "BNB"}
# Bases that are crypto even when quoted in a fiat currency (e.g. SOL/USD).
CRYPTO_BASES = {
    "BTC", "ETH", "SOL", "XRP", "ADA", "DOGE", "BNB", "LTC", "DOT", "AVAX",
    "MATIC", "LINK", "TRX", "BCH", "XLM", "ATOM", "ETC", "FIL", "APT", "ARB",
}
# Recognized fiat currencies for forex classification.
FIAT = {
    "USD", "EUR", "GBP", "JPY", "CHF", "AUD", "NZD", "CAD",
    "CNH", "SGD", "HKD", "SEK", "NOK", "MXN", "ZAR", "TRY",
}

_BINANCE_TF = {
    "M1": "1m", "M5": "5m", "M15": "15m", "M30": "30m",
    "H1": "1h", "H4": "4h", "D1": "1d", "W1": "1w",
}
_TWELVE_TF = {
    "M1": "1min", "M5": "5min", "M15": "15min", "M30": "30min",
    "H1": "1h", "H4": "4h", "D1": "1day", "W1": "1week",
}


def split_pair(pair: str) -> tuple[str, str]:
    base, _, quote = pair.strip().upper().partition("/")
    return base, quote


def classify(pair: str) -> str:
    base, quote = split_pair(pair)
    if not base or not quote:
        raise UnknownAssetError(f"Cannot parse pair: {pair!r}")
    if quote in CRYPTO_QUOTES or base in CRYPTO_BASES:
        return "crypto"
    if base in FIAT and quote in FIAT:
        return "forex"
    raise UnknownAssetError(f"Cannot classify pair as crypto or forex: {pair!r}")


def to_binance_symbol(pair: str) -> str:
    base, quote = split_pair(pair)
    return f"{base}{quote}"


def to_twelvedata_symbol(pair: str) -> str:
    base, quote = split_pair(pair)
    return f"{base}/{quote}"


def timeframe_to_interval(timeframe: str, provider: str) -> str:
    table = _BINANCE_TF if provider == "binance" else _TWELVE_TF
    tf = timeframe.strip().upper()
    if tf not in table:
        raise UnsupportedTimeframeError(
            f"Unsupported timeframe {timeframe!r}; "
            f"expected one of {sorted(table)}")
    return table[tf]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_classify.py -v`
Expected: PASS (all passed).

- [ ] **Step 5: Commit**

```bash
git add tradesight/market_data/classify.py tests/test_classify.py
git commit -m "feat: pair classification and provider symbol/timeframe mapping"
```

---

### Task 4: Candle cache (in-memory + Redis)

**Files:**
- Create: `tradesight/market_data/cache.py`
- Test: `tests/test_cache.py`

- [ ] **Step 1: Write the failing test**

`tests/test_cache.py`:

```python
from tradesight.market_data.cache import CandleCache


class Clock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t


def test_set_then_get_returns_value():
    clk = Clock()
    cache = CandleCache(now=clk)
    cache.set("k", [{"time": 1}], ttl=60)
    assert cache.get("k") == [{"time": 1}]


def test_get_missing_returns_none():
    assert CandleCache(now=Clock()).get("nope") is None


def test_value_expires_after_ttl():
    clk = Clock()
    cache = CandleCache(now=clk)
    cache.set("k", [{"time": 1}], ttl=60)
    clk.t += 61
    assert cache.get("k") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cache.py -v`
Expected: FAIL with import error.

- [ ] **Step 3: Write the implementation**

`tradesight/market_data/cache.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_cache.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add tradesight/market_data/cache.py tests/test_cache.py
git commit -m "feat: candle cache with in-memory TTL and Redis backends"
```

---

### Task 5: Binance client (crypto klines)

**Files:**
- Create: `tradesight/market_data/binance.py`
- Test: `tests/test_binance.py`

- [ ] **Step 1: Write the failing test**

`tests/test_binance.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_binance.py -v`
Expected: FAIL with import error.

- [ ] **Step 3: Write the implementation**

`tradesight/market_data/binance.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_binance.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add tradesight/market_data/binance.py tests/test_binance.py
git commit -m "feat: Binance crypto klines client"
```

---

### Task 6: Twelve Data client (forex OHLC)

**Files:**
- Create: `tradesight/market_data/twelvedata.py`
- Test: `tests/test_twelvedata.py`

- [ ] **Step 1: Write the failing test**

`tests/test_twelvedata.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_twelvedata.py -v`
Expected: FAIL with import error.

- [ ] **Step 3: Write the implementation**

`tradesight/market_data/twelvedata.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_twelvedata.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add tradesight/market_data/twelvedata.py tests/test_twelvedata.py
git commit -m "feat: Twelve Data forex OHLC client"
```

---

### Task 7: Market-data service (routing + caching)

**Files:**
- Create: `tradesight/market_data/service.py`
- Test: `tests/test_market_service.py`

- [ ] **Step 1: Write the failing test**

`tests/test_market_service.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_market_service.py -v`
Expected: FAIL with import error.

- [ ] **Step 3: Write the implementation**

`tradesight/market_data/service.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_market_service.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add tradesight/market_data/service.py tests/test_market_service.py
git commit -m "feat: market-data service with provider routing and caching"
```

---

### Task 8: Analyzer `news_provider` hook + `NewsService.report_or_none`

**Files:**
- Modify: `tradesight/analyzer.py` (`analyze` method, ~lines 150-196)
- Modify: `tradesight/news.py` (add `report_or_none`)
- Test: `tests/test_analyzer.py` (add tests), `tests/test_news.py` (add test)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_analyzer.py` (the module-level fixtures `VISION`, `DECISION`, `NEWS_REPORT`, `cfg`, `session`, `FakeClient` already exist):

```python
def test_news_provider_fetches_for_detected_pair():
    client = FakeClient([VISION, DECISION])
    seen = {}

    def provider(pair):
        seen["pair"] = pair
        return NEWS_REPORT

    result = ChartAnalyzer(client, cfg()).analyze(
        "b64", session(), None, news_provider=provider)
    assert seen["pair"] == "XAU/USD"
    assert result.news_available is True
    assert result.news_impact == "Firm USD on jobs data pressures gold."


def test_news_provider_skipped_when_report_supplied():
    client = FakeClient([VISION, DECISION])
    called = []
    ChartAnalyzer(client, cfg()).analyze(
        "b64", session(), NEWS_REPORT, news_provider=lambda p: called.append(p))
    assert called == []  # explicit report wins; provider not invoked


def test_news_provider_none_result_marks_unavailable():
    client = FakeClient([VISION, DECISION])
    result = ChartAnalyzer(client, cfg()).analyze(
        "b64", session(), None, news_provider=lambda p: None)
    assert result.news_available is False
```

Append to `tests/test_news.py`:

```python
def test_report_or_none_returns_just_the_report():
    from tradesight.news import NewsService
    from tradesight.config import Config

    cfg = Config.load(env={"NIM_API_KEY": "n", "TAVILY_API_KEY": "t"})

    class _Svc(NewsService):
        def report(self, pair):  # stub the network path
            return ({"summary": "x"}, True)

    svc = _Svc(client=None, config=cfg)
    assert svc.report_or_none("EUR/USD") == {"summary": "x"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_analyzer.py -k news_provider tests/test_news.py -k report_or_none -v`
Expected: FAIL — `analyze()` got an unexpected keyword `news_provider`; `NewsService` has no `report_or_none`.

- [ ] **Step 3: Add `news_provider` to `ChartAnalyzer.analyze`**

In `tradesight/analyzer.py`, change the `analyze` signature (currently `def analyze(self, image_b64, session, news_report, on_stage=None)`) to:

```python
    def analyze(self, image_b64: str, session: SessionInfo,
                news_report: Optional[dict] = None,
                on_stage: Optional[Any] = None,
                news_provider: Optional[Any] = None) -> Analysis:
        news_available = news_report is not None
```

Then, immediately AFTER the hollow-report guard block (the `if not (pair or _g(obs, "market_structure", "trend") ...)` block that returns the "Couldn't read the chart fully — retrying" `Analysis`) and BEFORE the `if on_stage: on_stage(f"Analyzing {pair or 'chart'}…")` line, insert:

```python
        # Web single-shot flow: fetch news for the pair vision just detected,
        # before reasoning. Desktop passes news_report directly and skips this.
        if news_report is None and news_provider is not None and pair:
            news_report = news_provider(pair)
            news_available = news_report is not None
```

(`Optional` and `Any` are already imported at the top of `analyzer.py`.)

- [ ] **Step 4: Add `report_or_none` to `NewsService`**

In `tradesight/news.py`, add this method to `NewsService` (after `report`):

```python
    def report_or_none(self, pair: str) -> Optional[dict]:
        """Convenience for use as an analyzer news_provider callable."""
        report, _ = self.report(pair)
        return report
```

(`Optional` is already imported in `news.py`.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_analyzer.py tests/test_news.py -v`
Expected: PASS (existing tests still pass + the new ones).

- [ ] **Step 6: Commit**

```bash
git add tradesight/analyzer.py tradesight/news.py tests/test_analyzer.py tests/test_news.py
git commit -m "feat: analyzer news_provider hook for single-shot web flow"
```

---

### Task 9: API settings (`ApiSettings` + `to_core_config`)

**Files:**
- Create: `tradesight/api/__init__.py`
- Create: `tradesight/api/settings.py`
- Test: `tests/test_api_settings.py`

- [ ] **Step 1: Write the failing test**

`tests/test_api_settings.py`:

```python
import pytest

from tradesight.api.settings import ApiSettings


def base_env():
    return {
        "NIM_API_KEY": "nim", "TAVILY_API_KEY": "tav", "GEMINI_API_KEY": "gem",
    }


def test_defaults_and_required():
    s = ApiSettings(_env_file=None, **base_env())
    assert s.vision_model == "gemini-2.5-flash"
    assert s.reasoning_model == "moonshotai/kimi-k2.6"
    assert s.news_model == "meta/llama-3.3-70b-instruct"
    assert s.analyse_rate_limit == "10/minute"


def test_to_core_config_points_vision_at_gemini():
    s = ApiSettings(_env_file=None, **base_env())
    core = s.to_core_config()
    assert core.nim_api_key == "nim"
    assert core.tavily_api_key == "tav"
    assert core.vision_api_key == "gem"
    assert "generativelanguage.googleapis.com" in core.vision_base_url
    assert core.vision_on_separate_provider is True
    assert core.reasoning_model == "moonshotai/kimi-k2.6"


def test_missing_required_raises():
    with pytest.raises(Exception):
        ApiSettings(_env_file=None, NIM_API_KEY="n", TAVILY_API_KEY="t")  # no GEMINI
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_api_settings.py -v`
Expected: FAIL with import error.

- [ ] **Step 3: Write the implementation**

`tradesight/api/__init__.py`:

```python
```

(empty file)

`tradesight/api/settings.py`:

```python
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict

from tradesight.config import Config, DEFAULT_BASE_URL, GEMINI_OPENAI_BASE


class ApiSettings(BaseSettings):
    """Fail-fast env validation for the web API.

    Required: NIM_API_KEY, TAVILY_API_KEY, GEMINI_API_KEY. Everything else has
    a sensible default. ``to_core_config`` adapts these into the dataclass the
    reused analyzer/news services expect, with vision pinned to Gemini.
    """

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore",
        case_sensitive=False)

    nim_api_key: str
    tavily_api_key: str
    gemini_api_key: str

    vision_model: str = "gemini-2.5-flash"
    vision_base_url: str = GEMINI_OPENAI_BASE
    reasoning_model: str = "moonshotai/kimi-k2.6"
    news_model: str = "meta/llama-3.3-70b-instruct"
    nim_base_url: str = DEFAULT_BASE_URL

    frontend_origin: str = "http://localhost:5173"
    redis_url: str = ""
    twelvedata_api_key: str = ""
    news_cache_ttl: int = 300
    analyse_rate_limit: str = "10/minute"

    def to_core_config(self) -> Config:
        return Config(
            nim_api_key=self.nim_api_key,
            tavily_api_key=self.tavily_api_key,
            base_url=self.nim_base_url,
            vision_model=self.vision_model,
            reasoning_model=self.reasoning_model,
            news_model=self.news_model,
            vision_base_url=self.vision_base_url,
            vision_api_key=self.gemini_api_key,
            news_cache_ttl=self.news_cache_ttl,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_api_settings.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add tradesight/api/__init__.py tradesight/api/settings.py tests/test_api_settings.py
git commit -m "feat: ApiSettings with fail-fast env validation and core Config adapter"
```

---

### Task 10: Request/response schemas with validation

**Files:**
- Create: `tradesight/api/schemas.py`
- Test: `tests/test_api_schemas.py`

- [ ] **Step 1: Write the failing test**

`tests/test_api_schemas.py`:

```python
import base64

import pytest
from pydantic import ValidationError

from tradesight.api.schemas import AnalyseRequest

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def test_valid_png_request():
    req = AnalyseRequest(image=b64(PNG_MAGIC + b"rest"), pair="EUR/USD")
    assert req.pair == "EUR/USD"


def test_pair_optional():
    assert AnalyseRequest(image=b64(PNG_MAGIC + b"x")).pair is None


def test_rejects_non_base64():
    with pytest.raises(ValidationError):
        AnalyseRequest(image="!!!not base64!!!")


def test_rejects_non_png():
    with pytest.raises(ValidationError):
        AnalyseRequest(image=b64(b"GIF89a not a png"))


def test_rejects_oversized_image():
    big = b64(PNG_MAGIC + b"\x00" * (10 * 1024 * 1024 + 1))
    with pytest.raises(ValidationError):
        AnalyseRequest(image=big)


def test_rejects_bad_pair_charset():
    with pytest.raises(ValidationError):
        AnalyseRequest(image=b64(PNG_MAGIC + b"x"), pair="EUR;DROP")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_api_schemas.py -v`
Expected: FAIL with import error.

- [ ] **Step 3: Write the implementation**

`tradesight/api/schemas.py`:

```python
from __future__ import annotations

import base64
import binascii
import re
from typing import Optional

from pydantic import BaseModel, field_validator

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_MAX_IMAGE_BYTES = 10 * 1024 * 1024
_PAIR_RE = re.compile(r"^[A-Za-z0-9/]{1,16}$")


class AnalyseRequest(BaseModel):
    image: str
    pair: Optional[str] = None

    @field_validator("image")
    @classmethod
    def _validate_image(cls, v: str) -> str:
        try:
            raw = base64.b64decode(v, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("image must be valid base64") from exc
        if len(raw) > _MAX_IMAGE_BYTES:
            raise ValueError("image exceeds 10 MB limit")
        if not raw.startswith(_PNG_MAGIC):
            raise ValueError("image must be a PNG")
        return v

    @field_validator("pair")
    @classmethod
    def _validate_pair(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if not _PAIR_RE.match(v):
            raise ValueError("pair must be 1-16 chars of [A-Za-z0-9/]")
        return v


class CandleModel(BaseModel):
    time: int
    open: float
    high: float
    low: float
    close: float
    volume: float


class MarketDataResponse(BaseModel):
    pair: str
    timeframe: str
    asset_class: str
    delayed: bool
    candles: list[CandleModel]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_api_schemas.py -v`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
git add tradesight/api/schemas.py tests/test_api_schemas.py
git commit -m "feat: API request/response schemas with image and pair validation"
```

---

### Task 11: Security-headers middleware and rate limiter

**Files:**
- Create: `tradesight/api/middleware.py`
- Create: `tradesight/api/ratelimit.py`

(No standalone test — exercised via the app integration tests in Tasks 13-15.)

- [ ] **Step 1: Write the middleware**

`tradesight/api/middleware.py`:

```python
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

_HEADERS = {
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains",
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Attaches baseline security headers to every API response."""

    def __init__(self, app: ASGIApp):
        super().__init__(app)

    async def dispatch(self, request, call_next):
        response = await call_next(request)
        for key, value in _HEADERS.items():
            response.headers.setdefault(key, value)
        return response
```

- [ ] **Step 2: Write the rate limiter helper**

`tradesight/api/ratelimit.py`:

```python
from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

# Module-level limiter so route decorators can reference it at import time.
limiter = Limiter(key_func=get_remote_address)


def analyse_limit(request) -> str:
    """Per-request limit string, read from app settings at call time."""
    return request.app.state.settings.analyse_rate_limit
```

- [ ] **Step 3: Verify imports resolve**

Run: `python -c "import tradesight.api.middleware, tradesight.api.ratelimit"`
Expected: no output, exit 0.

- [ ] **Step 4: Commit**

```bash
git add tradesight/api/middleware.py tradesight/api/ratelimit.py
git commit -m "feat: security-headers middleware and slowapi rate limiter"
```

---

### Task 12: Dependency providers

**Files:**
- Create: `tradesight/api/deps.py`

(No standalone test — exercised via app integration tests; these are one-line accessors.)

- [ ] **Step 1: Write the providers**

`tradesight/api/deps.py`:

```python
from __future__ import annotations

from fastapi import Request

from tradesight.analyzer import ChartAnalyzer
from tradesight.api.settings import ApiSettings
from tradesight.market_data.service import MarketDataService
from tradesight.news import NewsService


def get_settings(request: Request) -> ApiSettings:
    return request.app.state.settings


def get_analyzer(request: Request) -> ChartAnalyzer:
    return request.app.state.analyzer


def get_news(request: Request) -> NewsService:
    return request.app.state.news


def get_market_service(request: Request) -> MarketDataService:
    return request.app.state.market_service
```

- [ ] **Step 2: Verify imports resolve**

Run: `python -c "import tradesight.api.deps"`
Expected: no output, exit 0.

- [ ] **Step 3: Commit**

```bash
git add tradesight/api/deps.py
git commit -m "feat: FastAPI dependency providers backed by app.state"
```

---

### Task 13: App factory + health router

**Files:**
- Create: `tradesight/api/routers/__init__.py`
- Create: `tradesight/api/routers/health.py`
- Create: `tradesight/api/app.py`
- Test: `tests/test_api_health.py`

> **Build-order note:** `app.py` imports the `analyse` and `market_data` routers from Tasks 14-15. Implement Tasks 14 and 15 BEFORE running this task's test (the router files must exist for `app.py` to import). All three tasks are committed together-ish; if you prefer strict order, temporarily comment the two `include_router(analyse...)` / `include_router(market_data...)` lines to get health green, then uncomment after Task 15.

- [ ] **Step 1: Write the failing test**

`tests/test_api_health.py`:

```python
from fastapi.testclient import TestClient

from tradesight.api.app import create_app
from tradesight.api.settings import ApiSettings


def make_client():
    settings = ApiSettings(
        _env_file=None, NIM_API_KEY="n", TAVILY_API_KEY="t", GEMINI_API_KEY="g")
    app = create_app(settings)
    return TestClient(app)


def test_health_ok():
    resp = make_client().get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_security_headers_present():
    resp = make_client().get("/health")
    assert resp.headers["x-frame-options"] == "DENY"
    assert resp.headers["x-content-type-options"] == "nosniff"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_api_health.py -v`
Expected: FAIL with import error (`tradesight.api.app` missing).

- [ ] **Step 3: Write the health router**

`tradesight/api/routers/__init__.py`:

```python
```

(empty file)

`tradesight/api/routers/health.py`:

```python
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}
```

- [ ] **Step 4: Write the app factory**

`tradesight/api/app.py`:

```python
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from tradesight.analyzer import ChartAnalyzer
from tradesight.api.middleware import SecurityHeadersMiddleware
from tradesight.api.ratelimit import limiter
from tradesight.api.routers import analyse, health, market_data
from tradesight.api.settings import ApiSettings
from tradesight.market_data.binance import BinanceClient
from tradesight.market_data.cache import CandleCache
from tradesight.market_data.service import MarketDataService
from tradesight.market_data.twelvedata import TwelveDataClient
from tradesight.news import NewsService


def create_app(settings: ApiSettings | None = None) -> FastAPI:
    settings = settings or ApiSettings()
    core = settings.to_core_config()

    client = OpenAI(base_url=core.base_url, api_key=core.nim_api_key,
                    timeout=90.0, max_retries=1)
    if core.vision_on_separate_provider:
        vision_client = OpenAI(base_url=core.vision_base_url,
                               api_key=core.vision_api_key,
                               timeout=90.0, max_retries=1)
    else:
        vision_client = client

    cache = CandleCache(redis_url=settings.redis_url or None)
    binance = BinanceClient()
    twelvedata = (TwelveDataClient(settings.twelvedata_api_key)
                  if settings.twelvedata_api_key else None)

    app = FastAPI(title="TradeSight AI API")
    app.state.settings = settings
    app.state.analyzer = ChartAnalyzer(client, core, vision_client=vision_client)
    app.state.news = NewsService(client, core)
    app.state.market_service = MarketDataService(cache, binance, twelvedata)

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(analyse.router, prefix="/api")
    app.include_router(market_data.router, prefix="/api")
    return app
```

- [ ] **Step 5: Run test to verify it passes** (after Tasks 14-15 routers exist)

Run: `pytest tests/test_api_health.py -v`
Expected: PASS (2 passed).

- [ ] **Step 6: Commit**

```bash
git add tradesight/api/routers/__init__.py tradesight/api/routers/health.py tradesight/api/app.py tests/test_api_health.py
git commit -m "feat: FastAPI app factory, health endpoint, CORS, rate limiter wiring"
```

---

### Task 14: `/api/analyse` router

**Files:**
- Create: `tradesight/api/routers/analyse.py`
- Test: `tests/test_api_analyse.py`

- [ ] **Step 1: Write the failing test**

`tests/test_api_analyse.py`:

```python
import base64

from fastapi.testclient import TestClient

from tradesight.analyzer import Analysis
from tradesight.api.app import create_app
from tradesight.api.deps import get_analyzer, get_news
from tradesight.api.settings import ApiSettings

PNG = b"\x89PNG\r\n\x1a\n" + b"body"


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


class FakeAnalyzer:
    def __init__(self):
        self.kwargs = None

    def analyze(self, image_b64, session, news_report=None,
                on_stage=None, news_provider=None):
        self.kwargs = {"news_report": news_report, "news_provider": news_provider}
        return Analysis(pair="EUR/USD", signal="BUY", confidence=70,
                        chart_detected=True)


class FakeNews:
    def report(self, pair):
        return ({"summary": "s"}, True)

    def report_or_none(self, pair):
        return {"summary": "s"}


def client_with(analyzer, news):
    settings = ApiSettings(
        _env_file=None, NIM_API_KEY="n", TAVILY_API_KEY="t", GEMINI_API_KEY="g")
    app = create_app(settings)
    app.dependency_overrides[get_analyzer] = lambda: analyzer
    app.dependency_overrides[get_news] = lambda: news
    return TestClient(app)


def test_analyse_returns_analysis_with_disclaimer():
    c = client_with(FakeAnalyzer(), FakeNews())
    resp = c.post("/api/analyse", json={"image": b64(PNG)})
    assert resp.status_code == 200
    body = resp.json()
    assert body["pair"] == "EUR/USD"
    assert body["signal"] == "BUY"
    assert "not financial advice" in body["disclaimer"].lower()


def test_analyse_uses_news_provider_when_no_pair():
    fa = FakeAnalyzer()
    c = client_with(fa, FakeNews())
    c.post("/api/analyse", json={"image": b64(PNG)})
    assert fa.kwargs["news_provider"] is not None
    assert fa.kwargs["news_report"] is None


def test_analyse_fetches_news_up_front_when_pair_given():
    fa = FakeAnalyzer()
    c = client_with(fa, FakeNews())
    c.post("/api/analyse", json={"image": b64(PNG), "pair": "EUR/USD"})
    assert fa.kwargs["news_report"] == {"summary": "s"}


def test_analyse_rejects_non_png():
    c = client_with(FakeAnalyzer(), FakeNews())
    resp = c.post("/api/analyse", json={"image": b64(b"notpng")})
    assert resp.status_code == 422
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_api_analyse.py -v`
Expected: FAIL with import error (`analyse` router missing).

- [ ] **Step 3: Write the implementation**

`tradesight/api/routers/analyse.py`:

```python
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request

from tradesight.api.deps import get_analyzer, get_news
from tradesight.api.ratelimit import analyse_limit, limiter
from tradesight.api.schemas import AnalyseRequest
from tradesight.context import SessionContext

router = APIRouter()

DISCLAIMER = "Educational use only — not financial advice."


@router.post("/analyse")
@limiter.limit(analyse_limit)
def analyse(request: Request, body: AnalyseRequest,
            analyzer=Depends(get_analyzer), news=Depends(get_news)) -> dict:
    session = SessionContext.describe(datetime.now(timezone.utc))
    if body.pair:
        report, _ = news.report(body.pair)
        result = analyzer.analyze(body.image, session, news_report=report)
    else:
        result = analyzer.analyze(
            body.image, session, news_provider=news.report_or_none)

    data = asdict(result)
    data["updated_at"] = result.updated_at.isoformat()
    data["disclaimer"] = DISCLAIMER
    return data
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_api_analyse.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add tradesight/api/routers/analyse.py tests/test_api_analyse.py
git commit -m "feat: /api/analyse endpoint with news routing and disclaimer"
```

---

### Task 15: `/api/market-data` router

**Files:**
- Create: `tradesight/api/routers/market_data.py`
- Test: `tests/test_api_market_data.py`

- [ ] **Step 1: Write the failing test**

`tests/test_api_market_data.py`:

```python
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
        _env_file=None, NIM_API_KEY="n", TAVILY_API_KEY="t", GEMINI_API_KEY="g")
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_api_market_data.py -v`
Expected: FAIL with import error (`market_data` router missing).

- [ ] **Step 3: Write the implementation**

`tradesight/api/routers/market_data.py`:

```python
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from tradesight.api.deps import get_market_service
from tradesight.api.schemas import MarketDataResponse
from tradesight.market_data.errors import (
    ForexNotConfiguredError, ProviderError, UnknownAssetError,
    UnsupportedTimeframeError,
)

router = APIRouter()


@router.get("/market-data", response_model=MarketDataResponse)
def market_data(pair: str, timeframe: str,
                svc=Depends(get_market_service)) -> MarketDataResponse:
    try:
        candles, asset, delayed = svc.get_candles(pair, timeframe)
    except (UnknownAssetError, UnsupportedTimeframeError,
            ForexNotConfiguredError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return MarketDataResponse(
        pair=pair, timeframe=timeframe, asset_class=asset,
        delayed=delayed, candles=candles)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_api_market_data.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add tradesight/api/routers/market_data.py tests/test_api_market_data.py
git commit -m "feat: /api/market-data endpoint with error mapping"
```

---

### Task 16: Full suite, run target, README note

**Files:**
- Modify: `README.md` (create if absent)

- [ ] **Step 1: Run the entire test suite**

Run: `pytest -v`
Expected: ALL tests pass (existing desktop tests + all new market-data + API tests).

- [ ] **Step 2: Smoke-run the app factory import**

Run: `python -c "from tradesight.api.app import create_app; print('factory import ok')"`
Expected: prints `factory import ok` (no network/keys needed for import).

- [ ] **Step 3: Document the run command**

Add a "Web API" section to `README.md` (create the file if it does not exist):

````markdown
## Web API (backend vertical)

Copy `.env.example` to `.env` and fill in `NIM_API_KEY`, `TAVILY_API_KEY`,
`GEMINI_API_KEY` (and optionally `TWELVEDATA_API_KEY`, `REDIS_URL`). Then:

```bash
uvicorn "tradesight.api.app:create_app" --factory --reload
```

- `GET  /health` — liveness
- `POST /api/analyse` — `{ "image": "<base64 PNG>", "pair": "EUR/USD"? }`
- `GET  /api/market-data?pair=BTC/USDT&timeframe=H1`

Crypto (Binance) works with no key. Forex (Twelve Data) requires
`TWELVEDATA_API_KEY` and is marked `delayed: true`. **Educational use only —
not financial advice.**
````

- [ ] **Step 4: Manual smoke test (optional, needs real keys)**

Run: `uvicorn "tradesight.api.app:create_app" --factory` then in another shell
`curl "http://127.0.0.1:8000/api/market-data?pair=BTC/USDT&timeframe=H1"`
Expected: JSON with `asset_class: "crypto"` and a non-empty `candles` array.

- [ ] **Step 5: Commit**

```bash
git add README.md
git commit -m "docs: web API run instructions"
```

---

## Self-Review Notes

**Spec coverage:** FastAPI foundation (Tasks 9-13, 16), analyzer port via reuse + `news_provider` hook (Task 8), market-data module incl. classify/cache/binance/twelvedata/service (Tasks 2-7), `/api/analyse` (Task 14), `/api/market-data` (Task 15), security headers + CORS + rate limit (Tasks 11, 13), `ApiSettings` fail-fast + `to_core_config` (Task 9), schemas/validation (Task 10), testing across all (every task), deps + env + run target (Tasks 1, 16). All spec sections map to a task.

**Cross-task type consistency:** `MarketDataService.get_candles` returns `(list[dict], str, bool)` — consumed identically in Task 14/15 tests and the market-data router. `Candle.as_dict()` shape matches `CandleModel` fields. `analyze(..., news_provider=...)` signature in Task 8 matches the call sites in Task 14's router and `FakeAnalyzer`. Error types (`UnknownAssetError`, `UnsupportedTimeframeError`, `ForexNotConfiguredError`, `ProviderError`) defined once in `errors.py` and imported everywhere.

**Build-order caveat (called out in Task 13):** `app.py` imports the `analyse` and `market_data` routers, so implement Tasks 14-15 before running Task 13's test (or temporarily comment those two `include_router` lines to get health green first).
