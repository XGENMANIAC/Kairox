from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

# (name, open_hour, close_hour) in UTC; close may be < open meaning overnight.
_SESSIONS = [
    ("Sydney", 21, 6),
    ("Tokyo", 0, 9),
    ("London", 7, 16),
    ("New York", 12, 21),
]
_OPEN_HOURS = {"Sydney": 21, "Tokyo": 0, "London": 7, "New York": 12}
_PRIORITY = ["London", "New York", "Tokyo", "Sydney"]
_WEEKDAY = ["Monday", "Tuesday", "Wednesday", "Thursday",
            "Friday", "Saturday", "Sunday"]


def _is_open(open_h: int, close_h: int, hour: int) -> bool:
    if open_h <= close_h:
        return open_h <= hour < close_h
    return hour >= open_h or hour < close_h  # overnight wrap


@dataclass
class SessionInfo:
    session: str
    is_overlap: bool
    minutes_to_next: int
    day_of_week: str
    caution: Optional[str]


class SessionContext:
    @staticmethod
    def describe(now_utc: datetime) -> SessionInfo:
        hour = now_utc.hour
        weekday = now_utc.weekday()  # Mon=0 .. Sun=6
        day_name = _WEEKDAY[weekday]

        weekend = weekday >= 5
        open_now = [] if weekend else [
            name for name, o, c in _SESSIONS if _is_open(o, c, hour)
        ]

        is_overlap = "London" in open_now and "New York" in open_now
        if is_overlap:
            session = "London/NY Overlap"
        else:
            session = next((s for s in _PRIORITY if s in open_now), "Off-hours")

        # minutes until the next session open time (today or wrapping to tomorrow)
        now_min = hour * 60 + now_utc.minute
        opens = sorted(h * 60 for h in _OPEN_HOURS.values())
        future = [m for m in opens if m > now_min]
        minutes_to_next = (future[0] - now_min) if future \
            else (opens[0] + 24 * 60 - now_min)

        caution = None
        if weekday == 0 and 6 <= hour < 9:
            caution = "Monday open — wait for direction"
        elif weekday == 4 and hour >= 19:
            caution = "Friday close — thin liquidity"

        return SessionInfo(
            session=session,
            is_overlap=is_overlap,
            minutes_to_next=minutes_to_next,
            day_of_week=day_name,
            caution=caution,
        )
