from tradesight.market_data.cache import CandleCache


class Clock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t


def test_set_then_get_returns_value():
    clk = Clock()
    cache = CandleCache(now=clk)
    cache.set("k", [{"time": 1}], ttl=60)
    assert cache.get("k") == [{"time": 1}]


def test_get_missing_returns_none():
    assert CandleCache(now=Clock()).get("nope") is None


def test_value_expires_after_ttl():
    clk = Clock()
    cache = CandleCache(now=clk)
    cache.set("k", [{"time": 1}], ttl=60)
    clk.t += 61
    assert cache.get("k") is None
