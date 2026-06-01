# TradeSight AI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Tkinter desktop overlay that captures the screen, reads a trading chart with NVIDIA NIM vision (llama-3.2-90b-vision), reasons over it with Kimi K2 (kimi-k2-instruct-0905) plus Tavily news and session context, and shows a structured BUY/SELL/HOLD call.

**Architecture:** Layered. A worker thread does all I/O (capture, two NIM calls, Tavily); Tkinter is touched only on the main thread; results cross via a `queue.Queue`. Analyzer is two-stage: vision perception → text reasoning, merged into one `Analysis` dataclass. APIs/clients are dependency-injected so logic is unit-testable without live keys.

**Tech Stack:** Python 3.13, `openai` (NVIDIA NIM, OpenAI-compatible), `mss` + `Pillow`, `requests` (Tavily), `python-dotenv`, Tkinter (stdlib), `pytest`.

---

## File Structure

```
tradesight/
├── __init__.py
├── config.py        Config dataclass + .env load/validation
├── context.py       SessionContext (pure session logic)
├── capture.py       CaptureService (mss grab + pixel-diff gate + base64)
├── prompts.py       VISION_SYSTEM_PROMPT, REASONING_SYSTEM_PROMPT
├── analyzer.py      Analysis dataclass + ChartAnalyzer (2-stage)
├── news.py          NewsService (Tavily + Kimi sentiment + cache)
├── overlay.py       Overlay (Tkinter UI)
└── main.py          wiring, worker thread, interval loop
tests/
├── __init__.py
├── test_context.py
├── test_capture.py
├── test_analyzer.py
└── test_news.py
requirements.txt
.env.example
pytest.ini
run.py                # convenience entry: python run.py
```

Conventions: package imports are `from tradesight.X import Y`. Run tests with `python -m pytest`. Every task ends with a commit.

---

## Task 0: Project scaffold

**Files:**
- Create: `requirements.txt`, `.env.example`, `pytest.ini`, `run.py`,
  `tradesight/__init__.py`, `tests/__init__.py`

- [ ] **Step 1: Create `requirements.txt`**

```
openai>=1.40
mss>=9.0
Pillow>=10.0
python-dotenv>=1.0
requests>=2.31
pytest>=8.0
```

- [ ] **Step 2: Create `.env.example`**

```
NIM_API_KEY=
TAVILY_API_KEY=
CAPTURE_INTERVAL=30
CAPTURE_REGION=full
VISION_MODEL=meta/llama-3.2-90b-vision-instruct
REASONING_MODEL=moonshotai/kimi-k2-instruct-0905
```

- [ ] **Step 3: Create `pytest.ini`**

```ini
[pytest]
testpaths = tests
python_files = test_*.py
```

- [ ] **Step 4: Create empty package files**

`tradesight/__init__.py` and `tests/__init__.py` are empty files.

- [ ] **Step 5: Create `run.py`**

```python
from tradesight.main import main

if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Install deps**

Run: `python -m pip install -r requirements.txt`
Expected: installs succeed.

- [ ] **Step 7: Commit**

```bash
git add requirements.txt .env.example pytest.ini run.py tradesight/__init__.py tests/__init__.py
git commit -m "chore: project scaffold"
```

---

## Task 1: config.py — Config load + validation

**Files:**
- Create: `tradesight/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config.py
import pytest
from tradesight.config import Config, ConfigError


def test_load_returns_config_with_required_keys():
    env = {"NIM_API_KEY": "nim123", "TAVILY_API_KEY": "tav456"}
    cfg = Config.load(env=env)
    assert cfg.nim_api_key == "nim123"
    assert cfg.tavily_api_key == "tav456"
    assert cfg.vision_model == "meta/llama-3.2-90b-vision-instruct"
    assert cfg.reasoning_model == "moonshotai/kimi-k2-instruct-0905"
    assert cfg.capture_interval == 30


def test_load_raises_when_key_missing():
    with pytest.raises(ConfigError) as exc:
        Config.load(env={"NIM_API_KEY": "only-one"})
    assert "TAVILY_API_KEY" in str(exc.value)


def test_load_reads_overrides_from_env():
    env = {
        "NIM_API_KEY": "n", "TAVILY_API_KEY": "t",
        "CAPTURE_INTERVAL": "15", "CAPTURE_REGION": "full",
        "VISION_MODEL": "custom/vision",
    }
    cfg = Config.load(env=env)
    assert cfg.capture_interval == 15
    assert cfg.vision_model == "custom/vision"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tradesight.config'`

- [ ] **Step 3: Write `tradesight/config.py`**

```python
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping, Optional

from dotenv import load_dotenv


class ConfigError(Exception):
    """Raised when required configuration is missing."""


@dataclass
class Config:
    nim_api_key: str
    tavily_api_key: str
    base_url: str = "https://integrate.api.nvidia.com/v1"
    vision_model: str = "meta/llama-3.2-90b-vision-instruct"
    reasoning_model: str = "moonshotai/kimi-k2-instruct-0905"
    capture_interval: int = 30
    capture_region: str = "full"
    pixel_diff_threshold: float = 2.0
    news_cache_ttl: int = 300
    user_id: str = "local"

    @classmethod
    def load(cls, env: Optional[Mapping[str, str]] = None) -> "Config":
        if env is None:
            load_dotenv()
            env = os.environ

        nim = env.get("NIM_API_KEY")
        tav = env.get("TAVILY_API_KEY")
        missing = [name for name, val in
                   (("NIM_API_KEY", nim), ("TAVILY_API_KEY", tav)) if not val]
        if missing:
            raise ConfigError(
                "Missing required environment variables: " + ", ".join(missing)
                + ". Copy .env.example to .env and fill them in."
            )

        return cls(
            nim_api_key=nim,
            tavily_api_key=tav,
            vision_model=env.get("VISION_MODEL",
                                 cls.__dataclass_fields__["vision_model"].default),
            reasoning_model=env.get("REASONING_MODEL",
                                    cls.__dataclass_fields__["reasoning_model"].default),
            capture_interval=int(env.get("CAPTURE_INTERVAL", 30)),
            capture_region=env.get("CAPTURE_REGION", "full"),
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_config.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add tradesight/config.py tests/test_config.py
git commit -m "feat: config load and validation"
```

---

## Task 2: context.py — SessionContext

**Files:**
- Create: `tradesight/context.py`
- Test: `tests/test_context.py`

Session windows (UTC): Sydney 21–06, Tokyo 00–09, London 07–16, New York 12–21.
Overlap = London AND New York both open (12–16). Primary session label priority
when several are open: Overlap > London > New York > Tokyo > Sydney; none → "Off-hours".
Session open times for `minutes_to_next`: Sydney 21:00, Tokyo 00:00, London 07:00, NY 12:00.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_context.py
from datetime import datetime, timezone

from tradesight.context import SessionContext


def at(y, m, d, h, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=timezone.utc)


def test_london_only_session():
    # Wednesday 2026-06-03, 08:00 UTC -> London open, NY closed
    info = SessionContext.describe(at(2026, 6, 3, 8))
    assert info.session == "London"
    assert info.is_overlap is False
    assert info.day_of_week == "Wednesday"
    assert info.caution is None


def test_london_ny_overlap():
    # Wednesday 13:00 UTC -> London + NY both open
    info = SessionContext.describe(at(2026, 6, 3, 13))
    assert info.session == "London/NY Overlap"
    assert info.is_overlap is True


def test_tokyo_session_overnight():
    # Wednesday 02:00 UTC -> Tokyo + Sydney open, Tokyo is primary
    info = SessionContext.describe(at(2026, 6, 3, 2))
    assert info.session == "Tokyo"
    assert info.is_overlap is False


def test_minutes_to_next_open():
    # 08:00 UTC -> next open is New York at 12:00 -> 240 minutes
    info = SessionContext.describe(at(2026, 6, 3, 8))
    assert info.minutes_to_next == 240


def test_monday_open_caution():
    # Monday 2026-06-01, 07:30 UTC
    info = SessionContext.describe(at(2026, 6, 1, 7, 30))
    assert info.caution == "Monday open — wait for direction"


def test_friday_close_caution():
    # Friday 2026-06-05, 20:00 UTC
    info = SessionContext.describe(at(2026, 6, 5, 20))
    assert info.caution == "Friday close — thin liquidity"


def test_offhours():
    # Saturday 2026-06-06, 10:00 UTC -> markets effectively closed
    info = SessionContext.describe(at(2026, 6, 6, 10))
    assert info.session == "Off-hours"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_context.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tradesight.context'`

- [ ] **Step 3: Write `tradesight/context.py`**

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

# (name, open_hour, close_hour) in UTC; close may be < open meaning overnight.
_SESSIONS = [
    ("Sydney", 21, 6),
    ("Tokyo", 0, 9),
    ("London", 7, 16),
    ("New York", 12, 21),
]
_OPEN_HOURS = {"Sydney": 21, "Tokyo": 0, "London": 7, "New York": 12}
_PRIORITY = ["London", "New York", "Tokyo", "Sydney"]
_WEEKDAY = ["Monday", "Tuesday", "Wednesday", "Thursday",
            "Friday", "Saturday", "Sunday"]


def _is_open(open_h: int, close_h: int, hour: int) -> bool:
    if open_h <= close_h:
        return open_h <= hour < close_h
    return hour >= open_h or hour < close_h  # overnight wrap


@dataclass
class SessionInfo:
    session: str
    is_overlap: bool
    minutes_to_next: int
    day_of_week: str
    caution: Optional[str]


class SessionContext:
    @staticmethod
    def describe(now_utc: datetime) -> SessionInfo:
        hour = now_utc.hour
        weekday = now_utc.weekday()  # Mon=0 .. Sun=6
        day_name = _WEEKDAY[weekday]

        weekend = weekday >= 5
        open_now = [] if weekend else [
            name for name, o, c in _SESSIONS if _is_open(o, c, hour)
        ]

        is_overlap = "London" in open_now and "New York" in open_now
        if is_overlap:
            session = "London/NY Overlap"
        else:
            session = next((s for s in _PRIORITY if s in open_now), "Off-hours")

        # minutes until the next session open time (today or wrapping to tomorrow)
        now_min = hour * 60 + now_utc.minute
        opens = sorted(h * 60 for h in _OPEN_HOURS.values())
        future = [m for m in opens if m > now_min]
        minutes_to_next = (future[0] - now_min) if future \
            else (opens[0] + 24 * 60 - now_min)

        caution = None
        if weekday == 0 and 6 <= hour < 9:
            caution = "Monday open — wait for direction"
        elif weekday == 4 and hour >= 19:
            caution = "Friday close — thin liquidity"

        return SessionInfo(
            session=session,
            is_overlap=is_overlap,
            minutes_to_next=minutes_to_next,
            day_of_week=day_name,
            caution=caution,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_context.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add tradesight/context.py tests/test_context.py
git commit -m "feat: session context logic"
```

---

## Task 3: capture.py — CaptureService

**Files:**
- Create: `tradesight/capture.py`
- Test: `tests/test_capture.py`

`has_changed` and `to_base64_png` are unit-tested with synthetic PIL images.
`grab()` uses `mss` (hardware) and is verified manually, not in unit tests.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_capture.py
import base64

from PIL import Image

from tradesight.capture import CaptureService


def solid(color):
    return Image.new("RGB", (320, 240), color)


def test_first_frame_always_changed():
    cap = CaptureService(diff_threshold=2.0)
    assert cap.has_changed(solid((0, 0, 0))) is True


def test_identical_frame_not_changed():
    cap = CaptureService(diff_threshold=2.0)
    cap.has_changed(solid((10, 10, 10)))
    assert cap.has_changed(solid((10, 10, 10))) is False


def test_large_change_detected():
    cap = CaptureService(diff_threshold=2.0)
    cap.has_changed(solid((0, 0, 0)))
    assert cap.has_changed(solid((255, 255, 255))) is True


def test_to_base64_png_roundtrips():
    cap = CaptureService()
    b64 = cap.to_base64_png(solid((1, 2, 3)))
    raw = base64.b64decode(b64)
    assert raw[:8] == b"\x89PNG\r\n\x1a\n"  # PNG magic bytes
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_capture.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tradesight.capture'`

- [ ] **Step 3: Write `tradesight/capture.py`**

```python
from __future__ import annotations

import base64
import io
from typing import Optional

import mss
from PIL import Image, ImageChops, ImageStat

_DIFF_SIZE = (64, 64)


class CaptureService:
    def __init__(self, region: str = "full", diff_threshold: float = 2.0):
        self.region = region
        self._threshold = diff_threshold
        self._last_small: Optional[Image.Image] = None

    def grab(self) -> Image.Image:
        with mss.mss() as sct:
            if isinstance(self.region, dict):
                monitor = self.region
            else:
                monitor = sct.monitors[1]  # primary monitor, full
            shot = sct.grab(monitor)
            return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")

    def has_changed(self, img: Image.Image) -> bool:
        small = img.convert("L").resize(_DIFF_SIZE)
        if self._last_small is None:
            self._last_small = small
            return True
        diff = ImageChops.difference(small, self._last_small)
        mean_delta = ImageStat.Stat(diff).mean[0]
        self._last_small = small
        return mean_delta >= self._threshold

    def to_base64_png(self, img: Image.Image) -> str:
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode("ascii")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_capture.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Manual smoke check of grab()**

Run: `python -c "from tradesight.capture import CaptureService; print(CaptureService().grab().size)"`
Expected: prints your screen resolution, e.g. `(1920, 1080)`.

- [ ] **Step 6: Commit**

```bash
git add tradesight/capture.py tests/test_capture.py
git commit -m "feat: screen capture with pixel-diff gate"
```

---

## Task 4: prompts.py — system prompts

**Files:**
- Create: `tradesight/prompts.py`
- Test: `tests/test_analyzer.py` imports these; no dedicated test (constants).

- [ ] **Step 1: Write `tradesight/prompts.py`**

```python
"""System prompts — the trading-behavior tuning surface.

VISION_SYSTEM_PROMPT drives Stage 1 (perception). REASONING_SYSTEM_PROMPT
drives Stage 2 (decision). Edit these to change how TradeSight reads and judges
charts; no logic depends on their wording.
"""

VISION_SYSTEM_PROMPT = """\
You are a meticulous trading-chart reader. You are shown a screenshot that may
contain a forex or crypto chart. Read the chart; do NOT give trading advice.

Report ONLY what is visibly present. If something is not visible, use null or
"not visible" — never guess prices or invent indicators.

Observe and report:
- Trading pair (e.g. EUR/USD, BTC/USDT) and timeframe (e.g. M15, H1, H4, D1).
- Trend & structure: higher-highs/higher-lows vs lower-highs/lower-lows,
  market-structure breaks, support/resistance, supply/demand zones, trendlines,
  channels.
- Indicators if shown (value + state): RSI (level and any divergence), MACD
  (line/signal/histogram, crossovers), MA/EMA (which periods, price vs MA,
  crosses), Bollinger Bands (squeeze/expansion, band-walk), Stochastic, ADX
  (trend strength), Ichimoku cloud, VWAP, volume (spikes/dry-up), Fibonacci
  retracement/extension levels.
- Chart patterns: head & shoulders (and inverse), double/triple top & bottom,
  triangles (ascending/descending/symmetrical), wedges, bull/bear flags,
  pennants, channels, cup & handle, rounding.
- Candlestick patterns on the last few candles: engulfing, doji,
  hammer/hanging man, shooting star, pin bar, morning/evening star, marubozu,
  harami, tweezer.
- Momentum: strong / weak / diverging.

If there is no trading chart in the image, return exactly: {"chart_detected": false}

Otherwise return ONLY valid JSON, no prose, in this shape:
{
  "chart_detected": true,
  "pair": "EUR/USD",
  "timeframe": "H1",
  "trend": "bullish|bearish|ranging",
  "support_levels": [1.0820, 1.0795],
  "resistance_levels": [1.0875, 1.0910],
  "patterns_detected": ["bull flag", "higher highs"],
  "indicators": {"rsi": "62, no divergence", "macd": "bullish crossover",
                 "ma": "price above 50 EMA"},
  "candlestick_signal": "bullish engulfing on last candle",
  "momentum": "strong"
}
"""

REASONING_SYSTEM_PROMPT = """\
You are a disciplined trading decision engine. You are given structured chart
observations (JSON), the current trading session, and a one-line news sentiment.
You do NOT see the chart yourself — reason only from the observations given.

Decision framework:
- Confluence: a high-confidence call needs trend, pattern, indicators,
  candlestick signal, and key levels to agree. If signals conflict, bias toward
  HOLD.
- Risk management: propose an entry zone, a stop beyond the invalidation level,
  and a target at the next support/resistance. Enforce a minimum reward:risk of
  about 1.5. If the reward:risk is poor, downgrade to HOLD.
- Confidence calibration: 5/5 confluence with session and news aligned ≈ 80%+;
  mixed signals ≈ 50–65%; conflicting ≈ HOLD with low confidence.
- Context weighting: favour setups during the London/NY overlap; be cautious on
  Monday open and Friday close; do not fade strong news sentiment.
- Every reasoning bullet must cite a specific observation that drove the call.

Return ONLY valid JSON, no prose, in this shape:
{
  "signal": "BUY|SELL|HOLD",
  "confidence": 74,
  "entry_zone": "1.0845 - 1.0850",
  "stop_loss": "1.0820",
  "take_profit": "1.0895",
  "reasoning": ["Bullish trend intact above 50 EMA", "Bull flag breakout",
                "RSI has room before overbought"],
  "news_impact": "Soft US CPI weakens USD, supports EUR/USD longs",
  "session_context": "London/NY overlap — high liquidity window"
}
"""
```

- [ ] **Step 2: Verify importable**

Run: `python -c "from tradesight.prompts import VISION_SYSTEM_PROMPT, REASONING_SYSTEM_PROMPT; print(len(VISION_SYSTEM_PROMPT), len(REASONING_SYSTEM_PROMPT))"`
Expected: prints two positive integers.

- [ ] **Step 3: Commit**

```bash
git add tradesight/prompts.py
git commit -m "feat: vision and reasoning system prompts"
```

---

## Task 5: analyzer.py — Analysis dataclass + two-stage ChartAnalyzer

**Files:**
- Create: `tradesight/analyzer.py`
- Test: `tests/test_analyzer.py`

`ChartAnalyzer` takes an injected OpenAI-compatible `client`. Tests pass a fake
client returning canned message content, so no live keys are needed. JSON parsing
(`_parse_json`) and merge are unit-tested directly.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_analyzer.py
import json

from tradesight.analyzer import Analysis, ChartAnalyzer
from tradesight.config import Config
from tradesight.context import SessionInfo


class _Msg:
    def __init__(self, content):
        self.message = type("M", (), {"content": content})


class _Resp:
    def __init__(self, content):
        self.choices = [_Msg(content)]


class FakeClient:
    """Returns queued responses for sequential chat.completions.create calls."""
    def __init__(self, contents):
        self._contents = list(contents)
        self.calls = []

        outer = self

        class _Completions:
            def create(self, **kwargs):
                outer.calls.append(kwargs)
                return _Resp(outer._contents.pop(0))

        self.chat = type("C", (), {"completions": _Completions()})()


def cfg():
    return Config.load(env={"NIM_API_KEY": "n", "TAVILY_API_KEY": "t"})


def session():
    return SessionInfo("London", False, 240, "Wednesday", None)


def test_parse_json_strips_code_fence():
    text = '```json\n{"a": 1}\n```'
    assert ChartAnalyzer._parse_json(text) == {"a": 1}


def test_parse_json_extracts_embedded_object():
    text = 'Sure! {"signal": "BUY", "confidence": 70} hope that helps'
    assert ChartAnalyzer._parse_json(text)["signal"] == "BUY"


def test_no_chart_short_circuits():
    client = FakeClient(['{"chart_detected": false}'])
    analyzer = ChartAnalyzer(client, cfg())
    result = analyzer.analyze("b64", session(), None)
    assert result.chart_detected is False
    assert len(client.calls) == 1  # reasoning stage skipped


def test_full_pipeline_merges_both_stages():
    vision = json.dumps({
        "chart_detected": True, "pair": "EUR/USD", "timeframe": "H1",
        "trend": "bullish", "support_levels": [1.08], "resistance_levels": [1.09],
        "patterns_detected": ["bull flag"], "indicators": {"rsi": "62"},
        "candlestick_signal": "bullish engulfing", "momentum": "strong",
    })
    decision = json.dumps({
        "signal": "BUY", "confidence": 74, "entry_zone": "1.085",
        "stop_loss": "1.082", "take_profit": "1.089",
        "reasoning": ["trend up", "flag breakout"],
        "news_impact": "USD soft", "session_context": "London",
    })
    client = FakeClient([vision, decision])
    analyzer = ChartAnalyzer(client, cfg())
    result = analyzer.analyze("b64", session(), "USD soft on CPI")

    assert isinstance(result, Analysis)
    assert result.pair == "EUR/USD"
    assert result.signal == "BUY"
    assert result.confidence == 74
    assert result.reasoning == ["trend up", "flag breakout"]
    assert result.news_available is True
    assert len(client.calls) == 2


def test_bad_json_then_error_state():
    # vision returns garbage twice (original + retry) -> error Analysis
    client = FakeClient(["not json at all", "still not json"])
    analyzer = ChartAnalyzer(client, cfg())
    result = analyzer.analyze("b64", session(), None)
    assert result.error is not None
    assert result.signal == "HOLD"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_analyzer.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tradesight.analyzer'`

- [ ] **Step 3: Write `tradesight/analyzer.py`**

```python
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from .config import Config
from .context import SessionInfo
from .prompts import REASONING_SYSTEM_PROMPT, VISION_SYSTEM_PROMPT

_JSON_OBJ = re.compile(r"\{.*\}", re.DOTALL)


@dataclass
class Analysis:
    pair: Optional[str] = None
    timeframe: Optional[str] = None
    trend: Optional[str] = None
    support_levels: list = field(default_factory=list)
    resistance_levels: list = field(default_factory=list)
    patterns_detected: list = field(default_factory=list)
    indicators: dict = field(default_factory=dict)
    candlestick_signal: Optional[str] = None
    momentum: Optional[str] = None
    signal: str = "HOLD"
    confidence: int = 0
    entry_zone: Optional[str] = None
    stop_loss: Optional[str] = None
    take_profit: Optional[str] = None
    reasoning: list = field(default_factory=list)
    news_impact: Optional[str] = None
    session_context: Optional[str] = None
    chart_detected: bool = True
    news_available: bool = True
    error: Optional[str] = None
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class ChartAnalyzer:
    def __init__(self, client: Any, config: Config):
        self._client = client
        self._cfg = config

    @staticmethod
    def _parse_json(text: str) -> dict:
        text = text.strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.lstrip().lower().startswith("json"):
                text = text.lstrip()[4:]
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            match = _JSON_OBJ.search(text)
            if match:
                return json.loads(match.group(0))
            raise

    def _chat(self, model: str, system: str, user_content: Any) -> dict:
        """One call with one repair retry on bad JSON."""
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ]
        resp = self._client.chat.completions.create(
            model=model, messages=messages, temperature=0.2, max_tokens=1024)
        content = resp.choices[0].message.content
        try:
            return self._parse_json(content)
        except json.JSONDecodeError:
            messages.append({"role": "assistant", "content": content})
            messages.append({"role": "user",
                             "content": "Return ONLY valid JSON. No prose."})
            resp = self._client.chat.completions.create(
                model=model, messages=messages, temperature=0.0, max_tokens=1024)
            return self._parse_json(resp.choices[0].message.content)

    def _vision(self, image_b64: str) -> dict:
        user = [
            {"type": "text", "text": "Read this chart and return JSON."},
            {"type": "image_url",
             "image_url": {"url": f"data:image/png;base64,{image_b64}"}},
        ]
        return self._chat(self._cfg.vision_model, VISION_SYSTEM_PROMPT, user)

    def _reason(self, obs: dict, session: SessionInfo,
                news: Optional[str]) -> dict:
        user = (
            f"Chart observations: {json.dumps(obs)}\n"
            f"Session: {session.session} (overlap={session.is_overlap}, "
            f"day={session.day_of_week}, caution={session.caution})\n"
            f"News sentiment: {news or 'unavailable'}\n"
            "Decide the trade and return JSON."
        )
        return self._chat(self._cfg.reasoning_model, REASONING_SYSTEM_PROMPT, user)

    def analyze(self, image_b64: str, session: SessionInfo,
                news: Optional[str]) -> Analysis:
        news_available = news is not None
        try:
            obs = self._vision(image_b64)
        except Exception as exc:  # noqa: BLE001 — surface as UI error, never crash
            return Analysis(chart_detected=True, error=f"vision: {exc}",
                            news_available=news_available)

        if obs.get("chart_detected") is False:
            return Analysis(chart_detected=False, news_available=news_available)

        try:
            decision = self._reason(obs, session, news)
        except Exception as exc:  # noqa: BLE001
            return Analysis(chart_detected=True, error=f"reasoning: {exc}",
                            news_available=news_available,
                            pair=obs.get("pair"), timeframe=obs.get("timeframe"))

        return Analysis(
            pair=obs.get("pair"),
            timeframe=obs.get("timeframe"),
            trend=obs.get("trend"),
            support_levels=obs.get("support_levels", []),
            resistance_levels=obs.get("resistance_levels", []),
            patterns_detected=obs.get("patterns_detected", []),
            indicators=obs.get("indicators", {}),
            candlestick_signal=obs.get("candlestick_signal"),
            momentum=obs.get("momentum"),
            signal=str(decision.get("signal", "HOLD")).upper(),
            confidence=int(decision.get("confidence", 0) or 0),
            entry_zone=decision.get("entry_zone"),
            stop_loss=decision.get("stop_loss"),
            take_profit=decision.get("take_profit"),
            reasoning=decision.get("reasoning", []),
            news_impact=decision.get("news_impact"),
            session_context=decision.get("session_context"),
            chart_detected=True,
            news_available=news_available,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_analyzer.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add tradesight/analyzer.py tests/test_analyzer.py
git commit -m "feat: two-stage chart analyzer"
```

---

## Task 6: news.py — NewsService

**Files:**
- Create: `tradesight/news.py`
- Test: `tests/test_news.py`

Tavily HTTP and the OpenAI client are injected so tests stay offline. Cache is
verified with an injected clock.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_news.py
from tradesight.config import Config
from tradesight.news import NewsService


class _Msg:
    def __init__(self, content):
        self.message = type("M", (), {"content": content})


class _Resp:
    def __init__(self, content):
        self.choices = [_Msg(content)]


class FakeClient:
    def __init__(self, content):
        outer = self
        self.calls = 0

        class _Completions:
            def create(self, **kwargs):
                outer.calls += 1
                return _Resp(content)

        self.chat = type("C", (), {"completions": _Completions()})()


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def cfg():
    return Config.load(env={"NIM_API_KEY": "n", "TAVILY_API_KEY": "t"})


def test_sentiment_fetches_and_summarizes():
    posts = []

    def fake_post(url, json=None, timeout=None):
        posts.append(json)
        return FakeResponse({"results": [
            {"title": "EUR rises", "content": "ECB hawkish"},
            {"title": "USD soft", "content": "CPI cools"},
        ]})

    client = FakeClient("USD weakness supports EUR/USD longs")
    svc = NewsService(client, cfg(), http_post=fake_post)
    text, available = svc.sentiment("EUR/USD")

    assert available is True
    assert "EUR/USD" in text or "EUR" in text
    assert posts[0]["query"]  # a query was sent to Tavily


def test_sentiment_cached_within_ttl():
    calls = {"n": 0}

    def fake_post(url, json=None, timeout=None):
        calls["n"] += 1
        return FakeResponse({"results": [{"title": "x", "content": "y"}]})

    clock = {"t": 1000.0}
    client = FakeClient("flat")
    svc = NewsService(client, cfg(), http_post=fake_post,
                      now=lambda: clock["t"])

    svc.sentiment("EUR/USD")
    svc.sentiment("EUR/USD")  # within TTL -> no second fetch
    assert calls["n"] == 1

    clock["t"] += 10_000  # past TTL
    svc.sentiment("EUR/USD")
    assert calls["n"] == 2


def test_tavily_failure_returns_unavailable():
    def fake_post(url, json=None, timeout=None):
        raise ConnectionError("down")

    svc = NewsService(FakeClient("x"), cfg(), http_post=fake_post)
    text, available = svc.sentiment("EUR/USD")
    assert text is None
    assert available is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_news.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tradesight.news'`

- [ ] **Step 3: Write `tradesight/news.py`**

```python
from __future__ import annotations

import time
from typing import Any, Callable, Optional

import requests

from .config import Config

_TAVILY_URL = "https://api.tavily.com/search"


class NewsService:
    def __init__(self, client: Any, config: Config,
                 http_post: Callable = requests.post,
                 now: Callable[[], float] = time.time):
        self._client = client
        self._cfg = config
        self._post = http_post
        self._now = now
        self._cache: dict[str, tuple[float, Optional[str]]] = {}

    def sentiment(self, pair: str) -> tuple[Optional[str], bool]:
        """Return (one-line sentiment, available). Cached per pair by TTL."""
        cached = self._cache.get(pair)
        if cached and (self._now() - cached[0]) < self._cfg.news_cache_ttl:
            return cached[1], cached[1] is not None

        try:
            headlines = self._fetch(pair)
            text = self._summarize(pair, headlines)
            self._cache[pair] = (self._now(), text)
            return text, True
        except Exception:  # noqa: BLE001 — news is optional; degrade gracefully
            self._cache[pair] = (self._now(), None)
            return None, False

    def _fetch(self, pair: str) -> list[str]:
        base, _, quote = pair.partition("/")
        query = f"{base} {quote} forex news today".strip()
        resp = self._post(
            _TAVILY_URL,
            json={"api_key": self._cfg.tavily_api_key, "query": query,
                  "topic": "news", "days": 2, "max_results": 3},
            timeout=15,
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])
        return [f"{r.get('title', '')}: {r.get('content', '')}" for r in results]

    def _summarize(self, pair: str, headlines: list[str]) -> str:
        joined = "\n".join(headlines) or "No notable headlines."
        resp = self._client.chat.completions.create(
            model=self._cfg.reasoning_model,
            messages=[
                {"role": "system",
                 "content": "You summarize forex news impact in one sentence."},
                {"role": "user",
                 "content": (f"In one sentence, the likely short-term impact on "
                             f"{pair} for traders:\n{joined}")},
            ],
            temperature=0.3, max_tokens=120,
        )
        return resp.choices[0].message.content.strip()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_news.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add tradesight/news.py tests/test_news.py
git commit -m "feat: Tavily news service with sentiment and cache"
```

---

## Task 7: overlay.py — Tkinter UI

**Files:**
- Create: `tradesight/overlay.py`

UI is verified manually (Tkinter isn't unit-tested here). The overlay renders an
`Analysis` and exposes callbacks; it owns no business logic.

- [ ] **Step 1: Write `tradesight/overlay.py`**

```python
from __future__ import annotations

import queue
import tkinter as tk
from datetime import datetime, timezone
from typing import Callable, Optional

from .analyzer import Analysis

_SIGNAL_COLORS = {"BUY": "#1db954", "SELL": "#e0245e", "HOLD": "#888888"}
_BG = "#15171c"
_FG = "#e6e6e6"


class Overlay:
    def __init__(self, ui_queue: "queue.Queue",
                 on_refresh: Callable[[], None],
                 on_settings: Optional[Callable[[], None]] = None):
        self._queue = ui_queue
        self._on_refresh = on_refresh
        self._on_settings = on_settings or (lambda: None)
        self._expanded = False
        self._status = "Starting…"

        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.92)
        self.root.configure(bg=_BG)
        self._place_right_edge()

        self._tab = tk.Frame(self.root, bg=_BG)
        self._panel = tk.Frame(self.root, bg=_BG)
        self._build_tab()
        self._build_panel()
        self._show_tab()

        self.root.after(100, self._drain)

    # ---- geometry ---------------------------------------------------------
    def _place_right_edge(self):
        self.root.update_idletasks()
        sw = self.root.winfo_screenwidth()
        self.root.geometry(f"60x30+{sw - 64}+200")

    def _build_tab(self):
        btn = tk.Label(self._tab, text="TradeSight ▶", bg=_BG, fg=_FG,
                       font=("Segoe UI", 8), cursor="hand2", padx=4, pady=6)
        btn.pack(fill="both", expand=True)
        btn.bind("<Button-1>", lambda _e: self._expand())

    def _build_panel(self):
        self._labels = {}
        header = tk.Frame(self._panel, bg=_BG)
        header.pack(fill="x")
        tk.Label(header, text="TradeSight AI", bg=_BG, fg=_FG,
                 font=("Segoe UI", 10, "bold")).pack(side="left", padx=6, pady=4)
        tk.Button(header, text="▼", command=self._collapse, bd=0, bg=_BG,
                  fg=_FG).pack(side="right", padx=2)

        def row(key, title):
            tk.Label(self._panel, text=title, bg=_BG, fg="#7a7f8a",
                     font=("Segoe UI", 7)).pack(anchor="w", padx=8)
            lbl = tk.Label(self._panel, text="—", bg=_BG, fg=_FG, justify="left",
                           wraplength=300, font=("Segoe UI", 9), anchor="w")
            lbl.pack(anchor="w", fill="x", padx=8)
            self._labels[key] = lbl

        row("pair", "PAIR DETECTED")
        row("session", "SESSION")
        self._signal = tk.Label(self._panel, text="—", bg=_BG, fg=_FG,
                                font=("Segoe UI", 16, "bold"))
        self._signal.pack(anchor="w", padx=8, pady=(6, 0))
        row("confidence", "CONFIDENCE")
        row("reasoning", "REASONING")
        row("news", "NEWS IMPACT")
        row("updated", "LAST UPDATED")

        btns = tk.Frame(self._panel, bg=_BG)
        btns.pack(fill="x", pady=6)
        tk.Button(btns, text="Refresh Now", command=self._on_refresh, bd=0,
                  bg="#2a2f3a", fg=_FG).pack(side="left", padx=8)
        tk.Button(btns, text="Settings", command=self._on_settings, bd=0,
                  bg="#2a2f3a", fg=_FG).pack(side="left")

        tk.Label(self._panel, text="⚠ Not financial advice — AI can misread charts",
                 bg=_BG, fg="#7a7f8a", font=("Segoe UI", 7)).pack(pady=(2, 6))

    # ---- state transitions ------------------------------------------------
    def _show_tab(self):
        self._panel.pack_forget()
        self._tab.pack(fill="both", expand=True)

    def _expand(self):
        self._expanded = True
        self._tab.pack_forget()
        sw = self.root.winfo_screenwidth()
        self.root.geometry(f"320x480+{sw - 332}+120")
        self._panel.pack(fill="both", expand=True)

    def _collapse(self):
        self._expanded = False
        self._place_right_edge()
        self._show_tab()

    # ---- rendering --------------------------------------------------------
    def set_status(self, text: str):
        self._status = text

    def render(self, a: Analysis):
        if not a.chart_detected:
            self._signal.configure(text="—", fg=_FG)
            self._labels["pair"].configure(text="No chart detected on screen")
            return
        if a.error:
            self._labels["pair"].configure(text="Analysis unavailable — retrying")
            return
        self._labels["pair"].configure(text=f"{a.pair or '—'}  {a.timeframe or ''}")
        self._labels["session"].configure(text=a.session_context or "—")
        self._signal.configure(text=a.signal,
                               fg=_SIGNAL_COLORS.get(a.signal, _FG))
        self._labels["confidence"].configure(text=f"{a.confidence}%")
        bullets = "\n".join(f"• {r}" for r in (a.reasoning or [])) or "—"
        self._labels["reasoning"].configure(text=bullets)
        news = a.news_impact or ("news unavailable" if not a.news_available else "—")
        self._labels["news"].configure(text=news)
        stamp = a.updated_at.astimezone(timezone.utc).strftime("%H:%M:%S UTC")
        self._labels["updated"].configure(text=stamp)

    def _drain(self):
        try:
            while True:
                item = self._queue.get_nowait()
                if isinstance(item, Analysis):
                    self.render(item)
                elif isinstance(item, str):
                    self.set_status(item)
                    if not self._expanded:
                        pass
        except queue.Empty:
            pass
        self.root.after(100, self._drain)

    def run(self):
        self.root.mainloop()
```

- [ ] **Step 2: Manual UI smoke test**

Create a throwaway check (do not commit it):
Run:
```bash
python -c "import queue; from tradesight.overlay import Overlay; from tradesight.analyzer import Analysis; q=queue.Queue(); o=Overlay(q, lambda: print('refresh')); q.put(Analysis(pair='EUR/USD', timeframe='H1', signal='BUY', confidence=72, reasoning=['trend up','flag breakout'], news_impact='USD soft', session_context='London')); o.run()"
```
Expected: a small "TradeSight ▶" tab appears on the right edge; clicking it expands to the panel showing EUR/USD, a green BUY, 72%, two reasoning bullets, the news line, a timestamp, Refresh/Settings buttons, and the "Not financial advice" footer. Close the window to end.

- [ ] **Step 3: Commit**

```bash
git add tradesight/overlay.py
git commit -m "feat: Tkinter overlay UI"
```

---

## Task 8: main.py — wiring, worker thread, interval loop

**Files:**
- Create: `tradesight/main.py`

Ties modules together. Worker thread runs the pipeline; UI runs on the main
thread; they communicate via `queue.Queue`. All per-cycle errors are logged and
turned into UI status, never crashes.

- [ ] **Step 1: Write `tradesight/main.py`**

```python
from __future__ import annotations

import logging
import queue
import threading
from datetime import datetime, timezone

from openai import OpenAI

from .analyzer import Analysis, ChartAnalyzer
from .capture import CaptureService
from .config import Config, ConfigError
from .context import SessionContext
from .news import NewsService

logging.basicConfig(
    filename="tradesight.log", level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("tradesight")


class TradeSightApp:
    def __init__(self, config: Config):
        self._cfg = config
        self._client = OpenAI(base_url=config.base_url, api_key=config.nim_api_key)
        self._capture = CaptureService(region=config.capture_region,
                                       diff_threshold=config.pixel_diff_threshold)
        self._analyzer = ChartAnalyzer(self._client, config)
        self._news = NewsService(self._client, config)
        self._ui_queue: "queue.Queue" = queue.Queue()
        self._stop = threading.Event()
        self._refresh_now = threading.Event()
        self._last_pair: str | None = None

        # Imported here so headless test environments can import this module.
        from .overlay import Overlay
        self._overlay = Overlay(self._ui_queue, on_refresh=self._request_refresh)

    def _request_refresh(self):
        self._refresh_now.set()

    def _one_cycle(self):
        img = self._capture.grab()
        if not self._capture.has_changed(img) and not self._refresh_now.is_set():
            return  # screen unchanged; skip API spend
        self._refresh_now.clear()

        session = SessionContext.describe(datetime.now(timezone.utc))
        news_text = None
        if self._last_pair:
            news_text, _ = self._news.sentiment(self._last_pair)

        b64 = self._capture.to_base64_png(img)
        result = self._analyzer.analyze(b64, session, news_text)
        if result.pair:
            self._last_pair = result.pair
        result.session_context = result.session_context or session.session
        self._ui_queue.put(result)

    def _worker(self):
        # Force the first cycle even if the screen looks static at startup.
        self._refresh_now.set()
        while not self._stop.is_set():
            try:
                self._one_cycle()
            except Exception as exc:  # noqa: BLE001 — keep the loop alive
                log.exception("cycle failed: %s", exc)
                self._ui_queue.put("Analysis unavailable — retrying")
            self._stop.wait(self._cfg.capture_interval)

    def run(self):
        worker = threading.Thread(target=self._worker, daemon=True)
        worker.start()
        try:
            self._overlay.run()  # blocks on Tk mainloop
        finally:
            self._stop.set()


def main():
    try:
        config = Config.load()
    except ConfigError as exc:
        print(f"[TradeSight] {exc}")
        return
    TradeSightApp(config).run()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify full test suite still passes**

Run: `python -m pytest -v`
Expected: all tests from Tasks 1–6 PASS (config, context, capture, analyzer, news).

- [ ] **Step 3: End-to-end manual run**

Pre-req: copy `.env.example` to `.env` and fill `NIM_API_KEY` and `TAVILY_API_KEY`.
Open a real trading chart (e.g. TradingView EUR/USD) on screen.
Run: `python run.py`
Expected: tab appears → click to expand → within ~one interval the panel fills
with the detected pair, a color-coded signal, confidence, reasoning bullets,
news line, and timestamp. Check `tradesight.log` for any errors.

- [ ] **Step 4: Commit**

```bash
git add tradesight/main.py
git commit -m "feat: wire overlay, worker loop, end-to-end app"
```

---

## Self-Review Notes

- **Spec coverage:** capture+diff (T3), two-stage analyzer + prompts (T4,T5), news+cache+Tavily (T6), session/overlap/caution (T2), overlay 8 sections + colors + disclaimer (T7), worker loop + error handling + logging (T8), config/.env/validation + user_id (T1). Dropped items (calendar scraping, FastAPI, auth) are explicitly out of scope in the spec.
- **Error handling:** NIM failure → error Analysis + "retrying"; no chart → chart_detected False; Tavily failure → news unavailable, chart-only; all logged to tradesight.log; never crashes the Tk loop.
- **Type consistency:** `Analysis`, `SessionInfo`, `Config`, `ChartAnalyzer.analyze(image_b64, session, news)`, `NewsService.sentiment(pair) -> (str|None, bool)`, `CaptureService.has_changed/grab/to_base64_png`, `Overlay(ui_queue, on_refresh, on_settings)` — names match across tasks.
- **No live keys in tests:** analyzer/news use injected fake clients and fake HTTP; only T3 grab() and T8 step 3 touch hardware/live APIs (manual).
```
