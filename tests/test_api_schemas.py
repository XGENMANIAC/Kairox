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
