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
