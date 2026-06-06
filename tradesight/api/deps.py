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
