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


VISION = json.dumps({
    "chart_detected": True,
    "metadata": {"pair": "XAU/USD", "timeframe": "D1", "confidence": 0.9},
    "market_structure": {"trend": "downtrend"},
    "key_levels": {"support": [4483.0], "resistance": [4570.0]},
    "chart_patterns": [{"name": "lower highs", "status": "forming"}],
    "candlestick_patterns": [
        {"name": "bearish engulfing", "candle_position": "at 4570 resistance"}],
    "indicators": {"rsi": {"visible": True, "value": 43}},
})

DECISION = json.dumps({
    "pair": "XAU/USD", "timeframe": "D1", "signal": "sell", "confidence": 68,
    "entry_zone": "4500 - 4510", "stop_loss": "4575", "take_profit": "4400",
    "risk_reward": 2.1,
    "confluence_scores": {"trend_structure": 0.8, "technical_weighted_total": 0.7},
    "session": {"name": "New York"},
    "news_integration": {"net_sentiment": "bearish", "freshest_catalyst": "USD firm",
                         "event_risk_imminent": False},
    "reasoning": ["Bearish trend below 50 EMA", "Bearish engulfing at resistance"],
    "invalidation_condition": "Close above 4575",
    "what_to_watch": "Reaction at 4483 support",
    "hold_reason": None,
})

NEWS_REPORT = {"net_sentiment": "bearish", "sentiment_strength": 0.6,
               "summary": "Firm USD on jobs data pressures gold.",
               "event_risk": {"event_risk_imminent": False}}


def test_parse_json_strips_code_fence():
    assert ChartAnalyzer._parse_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_parse_json_extracts_embedded_object():
    assert ChartAnalyzer._parse_json('ok {"signal": "BUY"} bye')["signal"] == "BUY"


def test_no_chart_short_circuits():
    client = FakeClient(['{"chart_detected": false}'])
    result = ChartAnalyzer(client, cfg()).analyze("b64", session(), None)
    assert result.chart_detected is False
    assert len(client.calls) == 1  # reasoning stage skipped


def test_full_pipeline_maps_nested_schemas():
    client = FakeClient([VISION, DECISION])
    result = ChartAnalyzer(client, cfg()).analyze("b64", session(), NEWS_REPORT)

    assert isinstance(result, Analysis)
    # vision (nested -> flat)
    assert result.pair == "XAU/USD"
    assert result.timeframe == "D1"
    assert result.trend == "downtrend"
    assert result.support_levels == [4483.0]
    assert result.patterns_detected == ["lower highs"]
    assert result.candlestick_signal == "bearish engulfing (at 4570 resistance)"
    # decision
    assert result.signal == "SELL"  # upper-cased
    assert result.confidence == 68
    assert result.risk_reward == 2.1
    assert result.invalidation_condition == "Close above 4575"
    assert result.what_to_watch == "Reaction at 4483 support"
    assert result.confluence["technical_weighted_total"] == 0.7
    # news + session
    assert result.news_impact == "Firm USD on jobs data pressures gold."
    assert result.news_sentiment == "bearish"
    assert result.event_risk_imminent is False
    assert result.session_context == "New York"
    assert result.news_available is True
    assert len(client.calls) == 2


def test_event_risk_from_news_report_when_decision_silent():
    decision = json.loads(DECISION)
    decision["news_integration"].pop("event_risk_imminent")
    news = dict(NEWS_REPORT, event_risk={"event_risk_imminent": True})
    client = FakeClient([VISION, json.dumps(decision)])
    result = ChartAnalyzer(client, cfg()).analyze("b64", session(), news)
    assert result.event_risk_imminent is True


def test_bad_json_then_error_state():
    client = FakeClient(["not json at all", "still not json"])
    result = ChartAnalyzer(client, cfg()).analyze("b64", session(), None)
    assert result.error is not None
    assert result.signal == "HOLD"
