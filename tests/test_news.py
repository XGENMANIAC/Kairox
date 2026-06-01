from tradesight.config import Config
from tradesight.news import NewsService


class _Msg:
    def __init__(self, content):
        self.message = type("M", (), {"content": content})


class _Resp:
    def __init__(self, content):
        self.choices = [_Msg(content)]


class FakeClient:
    def __init__(self, content):
        outer = self
        self.calls = 0

        class _Completions:
            def create(self, **kwargs):
                outer.calls += 1
                return _Resp(content)

        self.chat = type("C", (), {"completions": _Completions()})()


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def cfg():
    return Config.load(env={"NIM_API_KEY": "n", "TAVILY_API_KEY": "t"})


def test_sentiment_fetches_and_summarizes():
    posts = []

    def fake_post(url, json=None, timeout=None):
        posts.append(json)
        return FakeResponse({"results": [
            {"title": "EUR rises", "content": "ECB hawkish"},
            {"title": "USD soft", "content": "CPI cools"},
        ]})

    client = FakeClient("USD weakness supports EUR/USD longs")
    svc = NewsService(client, cfg(), http_post=fake_post)
    text, available = svc.sentiment("EUR/USD")

    assert available is True
    assert "EUR/USD" in text or "EUR" in text
    assert posts[0]["query"]  # a query was sent to Tavily


def test_sentiment_cached_within_ttl():
    calls = {"n": 0}

    def fake_post(url, json=None, timeout=None):
        calls["n"] += 1
        return FakeResponse({"results": [{"title": "x", "content": "y"}]})

    clock = {"t": 1000.0}
    client = FakeClient("flat")
    svc = NewsService(client, cfg(), http_post=fake_post,
                      now=lambda: clock["t"])

    svc.sentiment("EUR/USD")
    svc.sentiment("EUR/USD")  # within TTL -> no second fetch
    assert calls["n"] == 1

    clock["t"] += 10_000  # past TTL
    svc.sentiment("EUR/USD")
    assert calls["n"] == 2


def test_tavily_failure_returns_unavailable():
    def fake_post(url, json=None, timeout=None):
        raise ConnectionError("down")

    svc = NewsService(FakeClient("x"), cfg(), http_post=fake_post)
    text, available = svc.sentiment("EUR/USD")
    assert text is None
    assert available is False
