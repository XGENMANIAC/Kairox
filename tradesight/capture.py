from __future__ import annotations

import base64
import io
from typing import Optional

import mss
from PIL import Image, ImageChops, ImageStat

_DIFF_SIZE = (64, 64)
_MAX_DIM = 1280  # cap the long edge sent to the vision model (speed vs detail)


class CaptureService:
    def __init__(self, region: str = "full", diff_threshold: float = 2.0,
                 max_dim: int = _MAX_DIM):
        self.region = region
        self._threshold = diff_threshold
        self._max_dim = max_dim
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

    def _downscale(self, img: Image.Image) -> Image.Image:
        """Shrink so the long edge is at most max_dim — smaller image, faster
        vision call — while keeping chart text legible."""
        long_edge = max(img.size)
        if self._max_dim and long_edge > self._max_dim:
            scale = self._max_dim / long_edge
            new_size = (round(img.width * scale), round(img.height * scale))
            img = img.resize(new_size, Image.LANCZOS)
        return img

    def to_base64_png(self, img: Image.Image) -> str:
        buf = io.BytesIO()
        self._downscale(img).save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode("ascii")
