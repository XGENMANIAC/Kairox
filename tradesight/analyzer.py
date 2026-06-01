from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from .config import Config
from .context import SessionInfo
from .prompts import REASONING_SYSTEM_PROMPT, VISION_SYSTEM_PROMPT

_JSON_OBJ = re.compile(r"\{.*\}", re.DOTALL)


@dataclass
class Analysis:
    pair: Optional[str] = None
    timeframe: Optional[str] = None
    trend: Optional[str] = None
    support_levels: list = field(default_factory=list)
    resistance_levels: list = field(default_factory=list)
    patterns_detected: list = field(default_factory=list)
    indicators: dict = field(default_factory=dict)
    candlestick_signal: Optional[str] = None
    momentum: Optional[str] = None
    signal: str = "HOLD"
    confidence: int = 0
    entry_zone: Optional[str] = None
    stop_loss: Optional[str] = None
    take_profit: Optional[str] = None
    reasoning: list = field(default_factory=list)
    news_impact: Optional[str] = None
    session_context: Optional[str] = None
    chart_detected: bool = True
    news_available: bool = True
    error: Optional[str] = None
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class ChartAnalyzer:
    def __init__(self, client: Any, config: Config):
        self._client = client
        self._cfg = config

    @staticmethod
    def _parse_json(text: str) -> dict:
        text = text.strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.lstrip().lower().startswith("json"):
                text = text.lstrip()[4:]
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            match = _JSON_OBJ.search(text)
            if match:
                return json.loads(match.group(0))
            raise

    def _chat(self, model: str, system: str, user_content: Any) -> dict:
        """One call with one repair retry on bad JSON."""
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ]
        resp = self._client.chat.completions.create(
            model=model, messages=messages, temperature=0.2, max_tokens=1024)
        content = resp.choices[0].message.content
        try:
            return self._parse_json(content)
        except json.JSONDecodeError:
            messages.append({"role": "assistant", "content": content})
            messages.append({"role": "user",
                             "content": "Return ONLY valid JSON. No prose."})
            resp = self._client.chat.completions.create(
                model=model, messages=messages, temperature=0.0, max_tokens=1024)
            return self._parse_json(resp.choices[0].message.content)

    def _vision(self, image_b64: str) -> dict:
        user = [
            {"type": "text", "text": "Read this chart and return JSON."},
            {"type": "image_url",
             "image_url": {"url": f"data:image/png;base64,{image_b64}"}},
        ]
        return self._chat(self._cfg.vision_model, VISION_SYSTEM_PROMPT, user)

    def _reason(self, obs: dict, session: SessionInfo,
                news: Optional[str]) -> dict:
        user = (
            f"Chart observations: {json.dumps(obs)}\n"
            f"Session: {session.session} (overlap={session.is_overlap}, "
            f"day={session.day_of_week}, caution={session.caution})\n"
            f"News sentiment: {news or 'unavailable'}\n"
            "Decide the trade and return JSON."
        )
        return self._chat(self._cfg.reasoning_model, REASONING_SYSTEM_PROMPT, user)

    def analyze(self, image_b64: str, session: SessionInfo,
                news: Optional[str]) -> Analysis:
        news_available = news is not None
        try:
            obs = self._vision(image_b64)
        except Exception as exc:  # noqa: BLE001 — surface as UI error, never crash
            return Analysis(chart_detected=True, error=f"vision: {exc}",
                            news_available=news_available)

        if obs.get("chart_detected") is False:
            return Analysis(chart_detected=False, news_available=news_available)

        try:
            decision = self._reason(obs, session, news)
        except Exception as exc:  # noqa: BLE001
            return Analysis(chart_detected=True, error=f"reasoning: {exc}",
                            news_available=news_available,
                            pair=obs.get("pair"), timeframe=obs.get("timeframe"))

        return Analysis(
            pair=obs.get("pair"),
            timeframe=obs.get("timeframe"),
            trend=obs.get("trend"),
            support_levels=obs.get("support_levels", []),
            resistance_levels=obs.get("resistance_levels", []),
            patterns_detected=obs.get("patterns_detected", []),
            indicators=obs.get("indicators", {}),
            candlestick_signal=obs.get("candlestick_signal"),
            momentum=obs.get("momentum"),
            signal=str(decision.get("signal", "HOLD")).upper(),
            confidence=int(decision.get("confidence", 0) or 0),
            entry_zone=decision.get("entry_zone"),
            stop_loss=decision.get("stop_loss"),
            take_profit=decision.get("take_profit"),
            reasoning=decision.get("reasoning", []),
            news_impact=decision.get("news_impact"),
            session_context=decision.get("session_context"),
            chart_detected=True,
            news_available=news_available,
        )
