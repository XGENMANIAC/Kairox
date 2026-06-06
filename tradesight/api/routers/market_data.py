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
