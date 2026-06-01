from datetime import datetime, timezone

from tradesight.context import SessionContext


def at(y, m, d, h, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=timezone.utc)


def test_london_only_session():
    info = SessionContext.describe(at(2026, 6, 3, 8))
    assert info.session == "London"
    assert info.is_overlap is False
    assert info.day_of_week == "Wednesday"
    assert info.caution is None


def test_london_ny_overlap():
    info = SessionContext.describe(at(2026, 6, 3, 13))
    assert info.session == "London/NY Overlap"
    assert info.is_overlap is True


def test_tokyo_session_overnight():
    info = SessionContext.describe(at(2026, 6, 3, 2))
    assert info.session == "Tokyo"
    assert info.is_overlap is False


def test_minutes_to_next_open():
    info = SessionContext.describe(at(2026, 6, 3, 8))
    assert info.minutes_to_next == 240


def test_monday_open_caution():
    info = SessionContext.describe(at(2026, 6, 1, 7, 30))
    assert info.caution == "Monday open — wait for direction"


def test_friday_close_caution():
    info = SessionContext.describe(at(2026, 6, 5, 20))
    assert info.caution == "Friday close — thin liquidity"


def test_offhours():
    info = SessionContext.describe(at(2026, 6, 6, 10))
    assert info.session == "Off-hours"


def test_midnight_tokyo_sydney_tiebreak():
    # 00:00 UTC Wednesday: Sydney (21-06) + Tokyo (00-09) open -> Tokyo wins priority
    info = SessionContext.describe(at(2026, 6, 3, 0))
    assert info.session == "Tokyo"
    assert info.is_overlap is False
    assert info.minutes_to_next == 420  # next open London 07:00


def test_sydney_just_opened_wraps_to_tokyo():
    # 21:30 UTC Wednesday: Sydney just opened; next open Tokyo 00:00 -> 150 min (wrap)
    info = SessionContext.describe(at(2026, 6, 3, 21, 30))
    assert info.session == "Sydney"
    assert info.minutes_to_next == 150


def test_sydney_closes_at_six():
    # 06:30 UTC Wednesday: Sydney closed at 06:00, Tokyo still open
    info = SessionContext.describe(at(2026, 6, 3, 6, 30))
    assert info.session == "Tokyo"
    assert info.minutes_to_next == 30  # London 07:00


def test_london_closes_ny_continues():
    # 16:30 UTC Wednesday: London closed at 16:00, NY open, no overlap
    info = SessionContext.describe(at(2026, 6, 3, 16, 30))
    assert info.session == "New York"
    assert info.is_overlap is False
