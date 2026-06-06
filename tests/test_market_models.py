from tradesight.market_data.models import Candle


def test_candle_as_dict_has_lightweight_charts_shape():
    c = Candle(time=1733400000, open=1.0, high=2.0, low=0.5, close=1.5, volume=10.0)
    assert c.as_dict() == {
        "time": 1733400000, "open": 1.0, "high": 2.0,
        "low": 0.5, "close": 1.5, "volume": 10.0,
    }


def test_candle_time_is_int_epoch_seconds():
    c = Candle(time=1733400000, open=1, high=1, low=1, close=1, volume=0)
    assert isinstance(c.as_dict()["time"], int)
