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
