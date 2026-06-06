# TradeSight AI — Backend Vertical Design Spec

**Date:** 2026-06-06
**Status:** Approved for implementation planning
**Scope:** Sub-projects #1 (FastAPI foundation) + #2 (analyzer port) + #3 (market-data module)

## Summary

Stand up the web-SaaS backend as a FastAPI app **inside the existing
`tradesight/` package**, reusing the proven analysis logic (`analyzer`,
`news`, `context`, `prompts`, `jsonutil`, `config`) and adding a new
market-data module. Two working endpoints — `POST /api/analyse` and
`GET /api/market-data` — with **no auth yet** (auth/quota is sub-project #5).
This is the foundation every later sub-project (Supabase, auth, Lemon Squeezy
billing, frontend PWA) builds on.

This is the first of an 8-part decomposition of the full master prompt. Later
sub-projects each get their own spec → plan → build cycle.

## Locked Decisions (from brainstorming)

| Area | Decision |
|------|----------|
| Start point | Backend vertical (#1+#2+#3), no auth |
| Repo layout | FastAPI wraps the existing `tradesight/` package in place; reuse, don't copy |
| Desktop app | Retired — left in git history, no longer the entrypoint, untouched |
| Vision model | **Google Gemini Flash** (`gemini-2.5-flash`) via Gemini OpenAI-compatible endpoint |
| Reasoning model | **Kimi K2** (`moonshotai/kimi-k2.6`) via NVIDIA NIM |
| News model | **`meta/llama-3.3-70b-instruct`** via NVIDIA NIM + Tavily fetch |
| Crypto data | Binance public API (free, no key, real-time) |
| Forex data | Twelve Data free tier (delayed) |
| Cache | Upstash Redis when configured, in-memory TTL fallback otherwise |
| Billing (later #6) | **Lemon Squeezy** (Merchant of Record) — not Stripe |
| HTTP in market-data | `requests` (sync), consistent with existing code |

The existing code already supports the vision/reasoning/news model split via
`VISION_API_KEY` / `VISION_BASE_URL` and the `vision_model` /
`reasoning_model` / `news_model` config slots — so the analyzer port is
primarily a matter of wiring the right clients, not rewriting logic.

## Architecture & File Layout

```
tradesight/
  analyzer.py  news.py  context.py  prompts.py  jsonutil.py  config.py   # REUSED as-is
  capture.py  overlay.py  main.py  settings_window.py  settings.py       # retired desktop (left in git)
  api/
    __init__.py
    app.py            # create_app() factory: middleware, routers, lifespan
    settings.py       # ApiSettings (pydantic-settings) — fail-fast env validation; .to_core_config()
    clients.py        # builds OpenAI clients (vision=Gemini, reasoning+news=NIM) + analyzer/news singletons
    middleware.py     # security-headers middleware
    schemas.py        # Pydantic request/response models
    routers/
      __init__.py
      health.py       # GET /health
      analyse.py      # POST /api/analyse
      market_data.py  # GET /api/market-data
  market_data/
    __init__.py
    service.py        # MarketDataService.get_candles(pair, timeframe) — routes by asset class
    binance.py        # BinanceClient (crypto klines)
    twelvedata.py     # TwelveDataClient (forex OHLC)
    cache.py          # CandleCache — Upstash Redis if configured, else in-memory TTL fallback
    classify.py       # pair → crypto|forex + per-provider symbol/timeframe normalization
    models.py         # Candle model
```

### Config strategy

The desktop `tradesight.config.Config` dataclass is **left untouched**. A new
`tradesight/api/settings.py` defines `ApiSettings` (pydantic-settings) that:

- validates all API-relevant env on startup (fail fast, clear message),
- exposes `.to_core_config() -> tradesight.config.Config` to feed the reused
  `ChartAnalyzer` / `NewsService`.

`ApiSettings` fields (env-backed):

- `nim_api_key`, `tavily_api_key` (required)
- `gemini_api_key` (required for vision) → maps to `vision_api_key`
- `vision_model` (default `gemini-2.5-flash`), `vision_base_url`
  (default Gemini OpenAI base `https://generativelanguage.googleapis.com/v1beta/openai/`)
- `reasoning_model` (default `moonshotai/kimi-k2.6`)
- `news_model` (default `meta/llama-3.3-70b-instruct`)
- `nim_base_url` (default `https://integrate.api.nvidia.com/v1`)
- `frontend_origin` (default `http://localhost:5173`) — CORS allowlist
- `redis_url` (optional) — enables Upstash Redis cache
- `twelvedata_api_key` (optional; forex disabled with clear error if absent)
- `news_cache_ttl` (default 300)
- `analyse_rate_limit` (default `"10/minute"`)

`.to_core_config()` produces a `Config` with `vision_base_url`/`vision_api_key`
pointing at Gemini and `base_url`/`nim_api_key` pointing at NIM, so
`config.vision_on_separate_provider` is `True` and two OpenAI clients are built.

## `/api/analyse`

**Request** (`AnalyseRequest`):
```
{ "image": "<base64 PNG>", "pair": "EUR/USD" }   # pair optional
```
Validation: `image` is valid base64; decoded bytes ≤ 10 MB; decoded bytes start
with the PNG magic number (`\x89PNG\r\n\x1a\n`). `pair` (optional) length ≤ 16,
charset `[A-Za-z0-9/]`.

**Flow:**
1. Validate request (Pydantic).
2. `session = SessionContext.describe(datetime.now(timezone.utc))`.
3. If `pair` supplied: `news_report, _ = news.report(pair)` up front; call
   `analyzer.analyze(image_b64, session, news_report=news_report)`.
4. If `pair` not supplied: call
   `analyzer.analyze(image_b64, session, news_provider=news.report_or_none)`
   so the analyzer fetches news for the pair vision detects, before reasoning.
5. Return the `Analysis` serialized as JSON, including a constant
   `disclaimer: "Educational use only — not financial advice."` field.

**Targeted analyzer improvement (well-bounded):**
Add an optional `news_provider: Callable[[str], Optional[dict]] | None = None`
parameter to `ChartAnalyzer.analyze()`. After the pair is extracted from the
vision observations and before reasoning, if `news_report is None` and
`news_provider` is set, call `news_report = news_provider(pair)`. Existing
callers (desktop) are unaffected — the parameter defaults to `None` and the
current `news_report` path is unchanged. `NewsService` gets a thin
`report_or_none(pair) -> Optional[dict]` wrapper that returns just the report
(dropping the availability bool) for use as the provider callable.

**Responses:** `200` Analysis; `chart_detected: false` is a normal `200`;
`422` validation error. Upstream model failure surfaced as `Analysis.error` is
still returned as `200` with the error field set (matches the existing analyzer
contract — never crash). True request-level failures (bad base64) → `422`.

## `/api/market-data`

**Request:** `GET /api/market-data?pair=BTC/USDT&timeframe=H1`

**Response** (`MarketDataResponse`):
```
{
  "pair": "BTC/USDT",
  "timeframe": "H1",
  "asset_class": "crypto",
  "delayed": false,
  "candles": [
    {"time": 1733400000, "open": 0.0, "high": 0.0, "low": 0.0, "close": 0.0, "volume": 0.0}
  ]
}
```
`time` is a UNIX epoch (seconds) for Lightweight Charts compatibility. The
sample values above are synthetic placeholders.

**classify.py:**
- `classify(pair) -> "crypto" | "forex"`: crypto if quote is a known crypto
  quote (`USDT`, `USDC`, `BTC`, `ETH`, `BUSD`) or base is a known crypto asset;
  otherwise forex (fiat pair like `EUR/USD`). Unknown → `400`.
- `to_binance_symbol("BTC/USDT") -> "BTCUSDT"`.
- `to_twelvedata_symbol("EUR/USD") -> "EUR/USD"`.
- `timeframe_to_interval(tf, provider)`: maps `M1/M5/M15/M30/H1/H4/D1/W1` to
  each provider's interval string (Binance `1m..1w`, Twelve Data `1min..1week`).
  Unsupported tf → `400`.

**MarketDataService.get_candles(pair, timeframe):**
1. `asset = classify(pair)`.
2. Cache lookup `candles:{pair}:{tf}`; return on hit.
3. Miss → route to `BinanceClient` (crypto) or `TwelveDataClient` (forex);
   normalize to `list[Candle]`.
4. Store in cache with TTL (crypto ~60s, forex ~300s).
5. Return `(candles, asset, delayed)` where `delayed = asset == "forex"`.

**Caching keyed per pair+timeframe, shared across all callers** (master-prompt
survival rule — N users on EUR/USD H1 = one upstream fetch). `CandleCache`:
Upstash Redis (`redis` client) when `redis_url` set; otherwise an in-memory
`{key: (expires_at, value)}` dict with a `now()` injection point for tests.

**Forex without `twelvedata_api_key`:** `400` with a clear "forex data not
configured" message. Crypto always works (Binance needs no key).

**Errors:** unknown asset/symbol → `400`; unsupported timeframe → `400`;
upstream provider error/timeout → `502` with a clear message.

## Security Foundation (no auth yet — auth is #5)

- CORS locked to `frontend_origin` (credentials allowed, methods limited).
- Security-headers middleware on every response: `Strict-Transport-Security`,
  `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`,
  `Referrer-Policy: strict-origin-when-cross-origin`, baseline
  `Content-Security-Policy: default-src 'none'; frame-ancestors 'none'`
  (API-only; the PWA sets its own CSP).
- Request body size cap enforced via the 10 MB image validation.
- `slowapi` per-IP rate limit on `POST /api/analyse` (default `10/minute`),
  configurable via `analyse_rate_limit`.
- No secrets in any client-bundle (none exist in this layer); all keys are
  server-side env via `ApiSettings`, validated fail-fast at startup.

## Error Handling

- Upstream model failure inside the analyzer → returned as `Analysis` with
  `error` set, HTTP `200` (existing never-crash contract).
- Market-data upstream failure → `502` JSON `{ "detail": "..." }`.
- Validation failure → FastAPI `422`.
- Misconfiguration (missing required env) → app fails to start with a clear
  message (pydantic-settings).
- All unexpected exceptions → logged; generic `500` without leaking internals.

## Testing (no live keys)

- `market_data/classify.py` — asset classification + symbol + timeframe mapping
  (table-driven; includes unknown/unsupported → error cases).
- `market_data/cache.py` — set/get, TTL expiry, miss, with injected clock
  (in-memory path; Redis path mocked).
- `market_data/service.py` — `get_candles` with fake Binance/Twelve Data
  clients and a fake cache: routing, cache hit/miss, delayed flag, forex-without-
  key error.
- `api/routers/analyse.py` — FastAPI `TestClient` with dependency-overridden
  fake analyzer + news: valid request shape, base64/size/PNG validation,
  `chart_detected: false` passthrough, `pair`-supplied vs `news_provider` path,
  disclaimer present.
- `api/routers/market_data.py` — `TestClient` with overridden fake service:
  success shape, `delayed` flag, `400` on bad pair/tf, `502` on provider error.
- `api/routers/health.py` — `GET /health` returns `200`.
- `analyzer.py` — extend existing tests to cover the new `news_provider` hook
  (called with detected pair; skipped when `news_report` supplied).
- Existing `news`/`context`/`config` tests keep passing unchanged.

## New Dependencies

Add to `requirements.txt`:
```
fastapi>=0.110
uvicorn[standard]>=0.29
pydantic-settings>=2.0
redis>=5.0          # optional cache backend; in-memory fallback if REDIS_URL unset
slowapi>=0.1.9
httpx>=0.27         # FastAPI TestClient dependency
```
(`openai`, `requests`, `Pillow`, `python-dotenv`, `pytest` already present.)

## .env additions (`.env.example`)

```
# Existing
NIM_API_KEY=
TAVILY_API_KEY=
# Vision on Gemini
GEMINI_API_KEY=
VISION_MODEL=gemini-2.5-flash
# Models (NIM)
REASONING_MODEL=moonshotai/kimi-k2.6
NEWS_MODEL=meta/llama-3.3-70b-instruct
# Market data
TWELVEDATA_API_KEY=
# Infra
REDIS_URL=
FRONTEND_ORIGIN=http://localhost:5173
ANALYSE_RATE_LIMIT=10/minute
```

## Run

```
uvicorn "tradesight.api.app:create_app" --factory --reload
```

## Out of Scope (later sub-projects)

- Auth / JWT verification / per-user quota (#5)
- Supabase schema + RLS (#4)
- Lemon Squeezy checkout + webhooks (#6)
- React PWA frontend + Lightweight Charts canvas (#7)
- CI/CD + security deliverables docs (#8)
- Caching of analysis results (each screenshot is unique — never cached)
- Live/real-time forex feed (paid tier, later)
