import json

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
        self.last_user = None

        class _Completions:
            def create(self, **kwargs):
                outer.calls += 1
                outer.last_user = kwargs["messages"][-1]["content"]
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


REPORT_JSON = json.dumps({
    "pair": "EUR/USD", "net_sentiment": "bullish", "sentiment_strength": 0.7,
    "summary": "Soft USD supports EUR/USD.",
    "event_risk": {"event_risk_imminent": False},
})


def test_report_returns_parsed_dict_and_passes_dated_items():
    posts = []

    def fake_post(url, json=None, timeout=None):
        posts.append(json)
        return FakeResponse({"results": [
            {"title": "EUR rises", "content": "ECB hawkish",
             "url": "https://reuters.com/x", "published_date": "2026-06-02"},
        ]})

    client = FakeClient(REPORT_JSON)
    svc = NewsService(client, cfg(), http_post=fake_post)
    report, available = svc.report("EUR/USD")

    assert available is True
    assert report["net_sentiment"] == "bullish"
    # the news model received structured, dated, sourced items + currencies
    sent = json.loads(client.last_user)
    assert sent["base_currency"] == "EUR" and sent["quote_currency"] == "USD"
    assert sent["tavily_results"][0]["published_date"] == "2026-06-02"
    assert sent["tavily_results"][0]["source"] == "reuters.com"
    assert "current_utc_time" in sent


def test_report_cached_within_ttl():
    calls = {"n": 0}

    def fake_post(url, json=None, timeout=None):
        calls["n"] += 1
        return FakeResponse({"results": [{"title": "x", "content": "y",
                                          "url": "https://a.com"}]})

    clock = {"t": 1000.0}
    svc = NewsService(FakeClient(REPORT_JSON), cfg(), http_post=fake_post,
                      now=lambda: clock["t"])

    svc.report("EUR/USD")
    svc.report("EUR/USD")  # within TTL -> no second fetch
    assert calls["n"] == 1

    clock["t"] += 10_000  # past TTL
    svc.report("EUR/USD")
    assert calls["n"] == 2


def test_tavily_failure_returns_unavailable():
    def fake_post(url, json=None, timeout=None):
        raise ConnectionError("down")

    svc = NewsService(FakeClient(REPORT_JSON), cfg(), http_post=fake_post)
    report, available = svc.report("EUR/USD")
    assert report is None
    assert available is False


def test_report_or_none_returns_just_the_report():
    class _Svc(NewsService):
        def report(self, pair):  # stub the network path
            return ({"summary": "x"}, True)

    svc = _Svc(client=None, config=cfg())
    assert svc.report_or_none("EUR/USD") == {"summary": "x"}
