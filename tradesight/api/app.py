from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from tradesight.analyzer import ChartAnalyzer
from tradesight.api.middleware import SecurityHeadersMiddleware
from tradesight.api.ratelimit import limiter, set_analyse_limit
from tradesight.api.routers import analyse, health, market_data
from tradesight.api.settings import ApiSettings
from tradesight.market_data.binance import BinanceClient
from tradesight.market_data.cache import CandleCache
from tradesight.market_data.service import MarketDataService
from tradesight.market_data.twelvedata import TwelveDataClient
from tradesight.news import NewsService


def create_app(settings: ApiSettings | None = None) -> FastAPI:
    settings = settings or ApiSettings()
    set_analyse_limit(settings.analyse_rate_limit)
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
