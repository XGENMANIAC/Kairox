import json

from tradesight.analyzer import Analysis, ChartAnalyzer
from tradesight.config import Config
from tradesight.context import SessionInfo


class _Msg:
    def __init__(self, content):
        self.message = type("M", (), {"content": content})


class _Resp:
    def __init__(self, content):
        self.choices = [_Msg(content)]


class FakeClient:
    """Returns queued responses for sequential chat.completions.create calls."""
    def __init__(self, contents):
        self._contents = list(contents)
        self.calls = []

        outer = self

        class _Completions:
            def create(self, **kwargs):
                outer.calls.append(kwargs)
                return _Resp(outer._contents.pop(0))

        self.chat = type("C", (), {"completions": _Completions()})()


def cfg():
    return Config.load(env={"NIM_API_KEY": "n", "TAVILY_API_KEY": "t"})


def session():
    return SessionInfo("London", False, 240, "Wednesday", None)


def test_parse_json_strips_code_fence():
    text = '```json\n{"a": 1}\n```'
    assert ChartAnalyzer._parse_json(text) == {"a": 1}


def test_parse_json_extracts_embedded_object():
    text = 'Sure! {"signal": "BUY", "confidence": 70} hope that helps'
    assert ChartAnalyzer._parse_json(text)["signal"] == "BUY"


def test_no_chart_short_circuits():
    client = FakeClient(['{"chart_detected": false}'])
    analyzer = ChartAnalyzer(client, cfg())
    result = analyzer.analyze("b64", session(), None)
    assert result.chart_detected is False
    assert len(client.calls) == 1  # reasoning stage skipped


def test_full_pipeline_merges_both_stages():
    vision = json.dumps({
        "chart_detected": True, "pair": "EUR/USD", "timeframe": "H1",
        "trend": "bullish", "support_levels": [1.08], "resistance_levels": [1.09],
        "patterns_detected": ["bull flag"], "indicators": {"rsi": "62"},
        "candlestick_signal": "bullish engulfing", "momentum": "strong",
    })
    decision = json.dumps({
        "signal": "BUY", "confidence": 74, "entry_zone": "1.085",
        "stop_loss": "1.082", "take_profit": "1.089",
        "reasoning": ["trend up", "flag breakout"],
        "news_impact": "USD soft", "session_context": "London",
    })
    client = FakeClient([vision, decision])
    analyzer = ChartAnalyzer(client, cfg())
    result = analyzer.analyze("b64", session(), "USD soft on CPI")

    assert isinstance(result, Analysis)
    assert result.pair == "EUR/USD"
    assert result.signal == "BUY"
    assert result.confidence == 74
    assert result.reasoning == ["trend up", "flag breakout"]
    assert result.news_available is True
    assert len(client.calls) == 2


def test_bad_json_then_error_state():
    # vision returns garbage twice (original + retry) -> error Analysis
    client = FakeClient(["not json at all", "still not json"])
    analyzer = ChartAnalyzer(client, cfg())
    result = analyzer.analyze("b64", session(), None)
    assert result.error is not None
    assert result.signal == "HOLD"
