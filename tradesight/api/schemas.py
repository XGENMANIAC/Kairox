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
