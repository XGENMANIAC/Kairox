from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple


@dataclass
class PriceAxis:
    """Linear map between chart price and vertical pixel position, derived from
    a vision read of the price axis."""

    anchors: List[Tuple[float, float]]  # (price, pixel_y)
    plot: dict = field(default_factory=dict)  # {left,right,top,bottom}

    def is_valid(self) -> bool:
        if len(self.anchors) < 2:
            return False
        prices = {round(p, 6) for p, _ in self.anchors}
        return len(prices) >= 2

    def _endpoints(self):
        ordered = sorted(self.anchors, key=lambda a: a[0])
        return ordered[0], ordered[-1]

    def y_for(self, price: float) -> float:
        (p0, y0), (p1, y1) = self._endpoints()
        return y0 + (price - p0) * (y1 - y0) / (p1 - p0)

    @classmethod
    def from_calibration(cls, data: dict) -> "PriceAxis":
        anchors = []
        for a in data.get("price_axis_anchors", []) or []:
            try:
                anchors.append((float(a["price"]), float(a["pixel_y"])))
            except (KeyError, TypeError, ValueError):
                continue
        plot = data.get("plot_area") or {}
        return cls(anchors=anchors, plot=plot)
