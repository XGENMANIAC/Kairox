from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from .config import Config
from .context import SessionInfo
from .jsonutil import create_json, parse_json_object
from .prompts import REASONING_SYSTEM_PROMPT, VISION_SYSTEM_PROMPT


@dataclass
class Analysis:
    # --- Stage 1 (vision) observations, flattened for the UI ---
    pair: Optional[str] = None
    timeframe: Optional[str] = None
    trend: Optional[str] = None
    support_levels: list = field(default_factory=list)
    resistance_levels: list = field(default_factory=list)
    patterns_detected: list = field(default_factory=list)
    indicators: dict = field(default_factory=dict)
    candlestick_signal: Optional[str] = None
    momentum: Optional[str] = None
    # --- Stage 2 (reasoning) decision ---
    signal: str = "HOLD"
    confidence: int = 0
    entry_zone: Optional[str] = None
    stop_loss: Optional[str] = None
    take_profit: Optional[str] = None
    risk_reward: Optional[float] = None
    reasoning: list = field(default_factory=list)
    invalidation_condition: Optional[str] = None
    what_to_watch: Optional[str] = None
    hold_reason: Optional[str] = None
    confluence: dict = field(default_factory=dict)
    # --- news + session context ---
    news_impact: Optional[str] = None
    news_sentiment: Optional[str] = None
    event_risk_imminent: bool = False
    session_context: Optional[str] = None
    # --- status flags ---
    chart_detected: bool = True
    news_available: bool = True
    error: Optional[str] = None
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


def _g(d: Any, *path, default=None):
    """Safe nested getter: _g(obj, 'a', 'b') -> obj['a']['b'] or default."""
    cur = d
    for key in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
    return cur if cur is not None else default


class ChartAnalyzer:
    def __init__(self, client: Any, config: Config):
        self._client = client
        self._cfg = config

    @staticmethod
    def _parse_json(text: str) -> dict:
        return parse_json_object(text)

    def _chat(self, model: str, system: str, user_content: Any,
              force_json: bool = True) -> dict:
        """One call with one repair retry on bad JSON.

        force_json toggles response_format. The vision model is left OFF: in
        JSON mode it gets lazy and emits a bare ``{"chart_detected": true}``
        instead of the full schema, so we use a plain call + robust parsing for
        it. Text models (reasoning, news) keep JSON mode on — they honour it.
        """
        create = (create_json if force_json
                  else lambda c, m, msgs, **kw:
                  c.chat.completions.create(model=m, messages=msgs, **kw))
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ]
        resp = create(self._client, model, messages,
                      temperature=0.2, max_tokens=2048)
        content = resp.choices[0].message.content
        try:
            return parse_json_object(content)
        except (json.JSONDecodeError, TypeError):
            messages.append({"role": "assistant", "content": content or ""})
            messages.append({"role": "user",
                             "content": "Return ONLY valid JSON. No prose."})
            resp = create(self._client, model, messages,
                          temperature=0.0, max_tokens=2048)
            return parse_json_object(resp.choices[0].message.content)

    def _vision(self, image_b64: str) -> dict:
        user = [
            {"type": "text",
             "text": ("Analyze this chart and return the COMPLETE JSON report: "
                      "metadata (pair + timeframe at minimum), market_structure, "
                      "key_levels, chart_patterns, candlestick_patterns, and "
                      "indicators — populated from what you actually see. "
                      "Do not return only chart_detected.")},
            {"type": "image_url",
             "image_url": {"url": f"data:image/png;base64,{image_b64}"}},
        ]
        return self._chat(self._cfg.vision_model, VISION_SYSTEM_PROMPT, user,
                          force_json=False)

    def _reason(self, obs: dict, session: SessionInfo,
                news_report: Optional[dict]) -> dict:
        session_json = json.dumps({
            "session": session.session,
            "is_overlap": session.is_overlap,
            "minutes_to_next": session.minutes_to_next,
            "day_of_week": session.day_of_week,
            "caution": session.caution,
        })
        news_json = (json.dumps(news_report) if news_report is not None
                     else "No news report available — treat news as neutral.")
        user = (
            f"Vision report (Stage 1):\n{json.dumps(obs)}\n\n"
            f"News report (Stage 1.5):\n{news_json}\n\n"
            f"Session context:\n{session_json}\n\n"
            "Decide the trade and return JSON."
        )
        return self._chat(self._cfg.reasoning_model, REASONING_SYSTEM_PROMPT, user)

    @staticmethod
    def _candlestick_summary(obs: dict) -> Optional[str]:
        patterns = obs.get("candlestick_patterns") or []
        if not patterns or not isinstance(patterns[0], dict):
            return None
        first = patterns[0]
        name = first.get("name")
        pos = first.get("candle_position")
        if name and pos:
            return f"{name} ({pos})"
        return name

    def analyze(self, image_b64: str, session: SessionInfo,
                news_report: Optional[dict]) -> Analysis:
        news_available = news_report is not None
        try:
            obs = self._vision(image_b64)
        except (json.JSONDecodeError, TypeError):
            # Vision returned prose instead of JSON — it almost always does this
            # when it sees no chart. Treat as "no chart" rather than a hard error.
            return Analysis(chart_detected=False, news_available=news_available)
        except Exception as exc:  # noqa: BLE001 — surface as UI error, never crash
            return Analysis(error=f"vision: {exc}", news_available=news_available)

        if obs.get("chart_detected") is False:
            return Analysis(chart_detected=False, news_available=news_available)

        pair = _g(obs, "metadata", "pair")
        timeframe = _g(obs, "metadata", "timeframe")

        # Guard against a hollow vision report (e.g. a bare {"chart_detected":
        # true}). Without real observations the reasoning model can only emit a
        # meaningless 0%-confidence HOLD, so don't run it — flag for retry.
        if not (pair or _g(obs, "market_structure", "trend")
                or _g(obs, "key_levels", "support")
                or _g(obs, "key_levels", "resistance")):
            return Analysis(error="Couldn't read the chart fully — retrying",
                            news_available=news_available)

        try:
            decision = self._reason(obs, session, news_report)
        except Exception as exc:  # noqa: BLE001
            return Analysis(error=f"reasoning: {exc}", news_available=news_available,
                            pair=pair, timeframe=timeframe)

        ni = decision.get("news_integration") or {}
        event_risk = bool(ni.get("event_risk_imminent")
                          or _g(news_report or {}, "event_risk",
                                "event_risk_imminent", default=False))
        news_impact = (_g(news_report or {}, "summary")
                       or ni.get("freshest_catalyst"))
        news_sentiment = ni.get("net_sentiment") or _g(news_report or {},
                                                       "net_sentiment")

        return Analysis(
            pair=pair or decision.get("pair"),
            timeframe=timeframe or decision.get("timeframe"),
            trend=_g(obs, "market_structure", "trend"),
            support_levels=_g(obs, "key_levels", "support", default=[]),
            resistance_levels=_g(obs, "key_levels", "resistance", default=[]),
            patterns_detected=[p.get("name") for p in (obs.get("chart_patterns")
                               or []) if isinstance(p, dict) and p.get("name")],
            indicators=obs.get("indicators") or {},
            candlestick_signal=self._candlestick_summary(obs),
            signal=str(decision.get("signal", "HOLD")).upper(),
            confidence=int(decision.get("confidence", 0) or 0),
            entry_zone=decision.get("entry_zone"),
            stop_loss=decision.get("stop_loss"),
            take_profit=decision.get("take_profit"),
            risk_reward=decision.get("risk_reward"),
            reasoning=decision.get("reasoning") or [],
            invalidation_condition=decision.get("invalidation_condition"),
            what_to_watch=decision.get("what_to_watch"),
            hold_reason=decision.get("hold_reason"),
            confluence=decision.get("confluence_scores") or {},
            news_impact=news_impact,
            news_sentiment=news_sentiment,
            event_risk_imminent=event_risk,
            session_context=_g(decision, "session", "name") or session.session,
            chart_detected=True,
            news_available=news_available,
        )
