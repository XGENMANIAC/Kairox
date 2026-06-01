# TradeSight AI — Design Spec

**Date:** 2026-06-01
**Status:** Approved for implementation planning

## Summary

A lightweight Windows desktop overlay that captures the screen on an interval,
reads the visible trading chart with a vision model, fetches relevant news,
combines that with trading-session context, and emits a structured
BUY / SELL / HOLD recommendation with reasoning. Architected modular for a
future multi-user SaaS.

## Locked Decisions

| Area | Decision |
|------|----------|
| Vision model (perception) | `meta/llama-3.2-90b-vision-instruct` (NVIDIA NIM) |
| Reasoning model (decision) | `moonshotai/kimi-k2-instruct-0905` (NVIDIA NIM) — successor to the deprecated `kimi-k2-instruct` |
| Inference endpoint | `https://integrate.api.nvidia.com/v1` (OpenAI-compatible), single NIM key, one OpenAI client, two model IDs |
| News | Tavily REST API (`POST https://api.tavily.com/search`), called directly by the app |
| UI | Tkinter overlay (always-on-top, semi-transparent, collapsible) |
| Build approach | Incremental, each module proven before the next |
| Keys | Both `NIM_API_KEY` and `TAVILY_API_KEY` available |

## Architecture

UI never touches an API directly. A worker thread does all I/O; Tkinter is
touched only on the main thread; results cross the boundary via a
`queue.Queue` drained by an `.after(100ms)` poll.

```
main.py ─ owns refresh loop (interval), worker thread, AppState, wiring
   │
   ├─ capture.py    CaptureService   screen → PIL.Image (+ pixel-diff gate)
   ├─ context.py    SessionContext   UTC time → session/overlap/day (pure)
   ├─ analyzer.py   ChartAnalyzer    image+context+news → validated Analysis
   ├─ news.py       NewsService      pair → Tavily fetch → 1-line sentiment
   ├─ prompts.py    system prompts   VISION_* and REASONING_* (tuning surface)
   ├─ config.py     Config           .env load + validation + constants
   └─ overlay.py    Overlay (Tk)     renders AppState, fires callbacks
```

## Two-Stage Analyzer

Perception is split from judgment.

### Stage 1 — `VisionReader` (llama-3.2-90b-vision)
Input: base64 screenshot + `VISION_SYSTEM_PROMPT`.
Job: read the chart, do not judge it. Outputs observable fields only:
`pair, timeframe, trend, support_levels, resistance_levels,
patterns_detected, indicators, candlestick_signal, momentum`.
Returns `{"chart_detected": false}` when no chart is present → pipeline
short-circuits and the UI shows "No chart detected."

### Stage 2 — `TradeReasoner` (kimi-k2-instruct-0905, text-only)
Input: Stage-1 observations (JSON) + session context + news sentiment +
`REASONING_SYSTEM_PROMPT`.
Job: decide. Outputs judgment fields:
`signal, confidence, entry_zone, stop_loss, take_profit, reasoning[],
news_impact, session_context`.

`ChartAnalyzer` orchestrates both and merges into one validated `Analysis`
dataclass. Callers (`overlay`, `main`) see a single object.

JSON discipline: both prompts demand valid-JSON-only. `analyzer` validates
against the dataclass; on parse failure, one retry with a "return valid JSON
only" nudge, then an error state.

## Per-Cycle Data Flow

1. `CaptureService.grab()` → image. `has_changed()` pixel-diff gate; if below
   threshold, skip the whole pipeline and keep the prior result (saves API spend).
2. `SessionContext.describe(now_utc)` → session string (pure, instant).
3. Stage 1 vision → observations incl. `pair`.
4. `NewsService.sentiment(pair)` → cache-served if fresh (TTL ≈ 5 min), else
   Tavily + Kimi sentiment summary.
5. Stage 2 reasoning → decision.
6. Merge → `AppState` → worker pushes to queue → UI redraws on main thread.

A cold cycle is sequential (vision → news → reason) and may take a few seconds;
accepted over staleness because the diff-gate skips idle cycles and news cache
avoids refetching every interval.

## Modules

### config.py — `Config`
Loads `.env` (python-dotenv). Validates `NIM_API_KEY` and `TAVILY_API_KEY`
present at startup — fail loud with a clear message, not a mid-cycle crash.
Constants: `VISION_MODEL`, `REASONING_MODEL`, `BASE_URL`, `CAPTURE_INTERVAL`
(30s), `CAPTURE_REGION` (`full` | custom dict), `PIXEL_DIFF_THRESHOLD`,
`NEWS_CACHE_TTL`, `user_id` (default `"local"`, for future multi-user).

### capture.py — `CaptureService`
`mss` grab → `PIL.Image`. `grab()` returns image. `has_changed(img)` compares
mean per-pixel delta vs stored last frame against `PIXEL_DIFF_THRESHOLD`
(downscale to ~64px first — cheap, noise-tolerant). `to_base64_png(img)` for the
vision call. Supports `full` or custom `{top,left,width,height}` region.

### context.py — `SessionContext`
Pure, no I/O, unit-testable. `describe(now_utc)` →
`{session, is_overlap, minutes_to_next, day_of_week, caution}`.
`caution` flags Monday-open / Friday-close. Sessions: Sydney 21–06, Tokyo 00–09,
London 07–16, New York 12–21, London/NY overlap 12–16 (all UTC).
Economic-calendar scraping (forexfactory/investing.com) is **dropped** —
brittle, ToS-gray; Tavily news covers high-impact events. Can be added later
behind the news interface.

### news.py — `NewsService`
`sentiment(pair)`: split pair → Tavily REST `POST /search`
(`topic="news"`, `days=2`, top 3 headlines+summaries) → feed to Kimi for a
one-line "likely short-term impact on {pair}" summary. Cached per-pair with
`NEWS_CACHE_TTL`. On Tavily failure → return `None` + flag; pipeline proceeds
chart-only; UI notes "news unavailable."

### prompts.py — system prompts (the trading-behavior tuning surface)

`VISION_SYSTEM_PROMPT` — exhaustive observation checklist, report only what is
visible:
- Trend/structure: HH/HL vs LH/LL, structure breaks, S/R, supply/demand zones,
  trendlines, channels
- Indicators (value + state if shown): RSI (+divergence), MACD
  (line/signal/histogram, crossovers), MA/EMA (periods, price vs MA, crosses),
  Bollinger (squeeze/expansion, band walk), Stochastic, ADX, Ichimoku, VWAP,
  volume, Fibonacci retracement/extension
- Chart patterns: H&S (+inverse), double/triple top & bottom, triangles
  (asc/desc/sym), wedges, bull/bear flags, pennants, channels, cup & handle,
  rounding
- Candlesticks (last few): engulfing, doji, hammer/hanging man, shooting star,
  pin bar, morning/evening star, marubozu, harami, tweezer
- Discipline: `null`/"not visible" over guessing; note per-reading confidence;
  never invent price levels it cannot see

`REASONING_SYSTEM_PROMPT` — decision framework:
- Confluence scoring: trend + pattern + indicator + candlestick + level must
  agree for high confidence; conflicting → bias HOLD
- Risk management: entry zone, stop beyond invalidation, target at next S/R,
  enforce minimum R:R ≈ 1.5; poor R:R → downgrade to HOLD
- Confidence calibration rubric: 5/5 confluence + session + news aligned ≈ 80%+;
  mixed ≈ 50–65%; conflicting ≈ HOLD/low
- Context weighting: boost London/NY overlap; caution Monday-open/Friday-close;
  respect strong news sentiment
- Output strictly the decision JSON schema; reasoning cites the specific
  observations that drove the call

### overlay.py — `Overlay` (Tkinter)
Tab state (~60×30, right edge, `-topmost`, `-alpha` transparency) ⇄ panel
(~320×480) with the 8 spec sections: PAIR, SESSION, SIGNAL (color-coded
green/red/grey), CONFIDENCE, REASONING (3–5 bullets), NEWS IMPACT, LAST UPDATED,
and Refresh / Settings / Collapse buttons. Renders from `AppState` only; pushes
button events to callbacks `main` registers. Drains worker→UI `queue.Queue` via
`.after(100ms)`. Persistent **"⚠ Not financial advice"** footer. Render guards
against partial/missing fields; never raises into the Tk loop.

### main.py
Owns `AppState`, worker thread + `threading.Event` stop flag, interval loop,
wiring. Catches every per-cycle exception → logs to `tradesight.log` → sets a
UI status string ("Analysis unavailable — retrying"). Clean shutdown on window
close.

## Analysis Dataclass (merged output)

```
pair, timeframe, trend,
support_levels[], resistance_levels[],
patterns_detected[], indicators{}, candlestick_signal, momentum,   # Stage 1
signal, confidence, entry_zone, stop_loss, take_profit,
reasoning[], news_impact, session_context,                         # Stage 2
chart_detected: bool, error: str|None, news_available: bool, updated_at
```

## Error Handling

- NIM failure → "Analysis unavailable — retrying"; logged; UI stays alive
- No chart → "No chart detected on screen"
- Tavily failure → chart-only analysis, note in output
- All errors → `tradesight.log`
- Overlay never crashes; one retry on bad JSON before error state

## Testing

- `context.py` — real unit tests (pure logic)
- `capture` diff — two synthetic images
- `analyzer` / `news` — against saved sample JSON responses (no live keys)
- End-to-end — final manual run with real keys + a real chart on screen

## .env

```
NIM_API_KEY=
TAVILY_API_KEY=
CAPTURE_INTERVAL=30
CAPTURE_REGION=full
VISION_MODEL=meta/llama-3.2-90b-vision-instruct
REASONING_MODEL=moonshotai/kimi-k2-instruct-0905
```

## File Structure

```
tradesight/
├── main.py
├── overlay.py
├── capture.py
├── analyzer.py
├── news.py
├── context.py
├── prompts.py
├── config.py
├── .env
└── requirements.txt
```

## Future / Out of Scope (YAGNI now)

- Economic-calendar scraping
- FastAPI wrapper of analyzer for SaaS backend
- Per-user auth, API-key management, usage limits
- Electron/Tauri cross-platform overlay
- Pluggable multi-provider news interface
```
