# TradeSight AI

AI trading-chart analysis and learning tool. A vision model reads a chart
screenshot and returns a structured BUY/SELL/HOLD analysis with reasoning,
news sentiment, and trading-session context. **Educational use only — not
financial advice.**

## Web API (backend vertical)

Copy `.env.example` to `.env` and fill in `NIM_API_KEY`, `TAVILY_API_KEY`,
`GEMINI_API_KEY` (and optionally `TWELVEDATA_API_KEY`, `REDIS_URL`). Then:

```bash
uvicorn "tradesight.api.app:create_app" --factory --reload
```

Endpoints:

- `GET  /health` — liveness
- `POST /api/analyse` — body `{ "image": "<base64 PNG>", "pair": "EUR/USD"? }`
- `GET  /api/market-data?pair=BTC/USDT&timeframe=H1`

Models: **Gemini Flash** (vision), **Kimi K2** (reasoning), **llama-3.3-70b**
(news). Crypto data via Binance (no key, real-time); forex via Twelve Data
(requires `TWELVEDATA_API_KEY`, marked `delayed: true`). Market data is cached
per pair+timeframe (Upstash Redis if `REDIS_URL` is set, in-memory otherwise).

## Tests

```bash
python -m pytest -q
```

## Desktop app (retired)

The original Tkinter screen-overlay app (`tradesight/main.py`, `overlay.py`,
`capture.py`) is retired in favor of the web API above. It remains in git
history for reference.
