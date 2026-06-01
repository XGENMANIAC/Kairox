from __future__ import annotations

import time
from typing import Any, Callable, Optional

import requests

from .config import Config

_TAVILY_URL = "https://api.tavily.com/search"


class NewsService:
    def __init__(self, client: Any, config: Config,
                 http_post: Callable = requests.post,
                 now: Callable[[], float] = time.time):
        self._client = client
        self._cfg = config
        self._post = http_post
        self._now = now
        self._cache: dict[str, tuple[float, Optional[str]]] = {}

    def sentiment(self, pair: str) -> tuple[Optional[str], bool]:
        """Return (one-line sentiment, available). Cached per pair by TTL."""
        cached = self._cache.get(pair)
        if cached and (self._now() - cached[0]) < self._cfg.news_cache_ttl:
            return cached[1], cached[1] is not None

        try:
            headlines = self._fetch(pair)
            text = self._summarize(pair, headlines)
            self._cache[pair] = (self._now(), text)
            return text, True
        except Exception:  # noqa: BLE001 — news is optional; degrade gracefully
            self._cache[pair] = (self._now(), None)
            return None, False

    def _fetch(self, pair: str) -> list[str]:
        base, _, quote = pair.partition("/")
        query = f"{base} {quote} forex news today".strip()
        resp = self._post(
            _TAVILY_URL,
            json={"api_key": self._cfg.tavily_api_key, "query": query,
                  "topic": "news", "days": 2, "max_results": 3},
            timeout=15,
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])
        return [f"{r.get('title', '')}: {r.get('content', '')}" for r in results]

    def _summarize(self, pair: str, headlines: list[str]) -> str:
        joined = "\n".join(headlines) or "No notable headlines."
        resp = self._client.chat.completions.create(
            model=self._cfg.reasoning_model,
            messages=[
                {"role": "system",
                 "content": "You summarize forex news impact in one sentence."},
                {"role": "user",
                 "content": (f"In one sentence, the likely short-term impact on "
                             f"{pair} for traders:\n{joined}")},
            ],
            temperature=0.3, max_tokens=120,
        )
        return resp.choices[0].message.content.strip()
