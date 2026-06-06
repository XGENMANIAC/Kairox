from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any, Callable, Optional
from urllib.parse import urlparse

import requests

from .config import Config
from .jsonutil import create_json, parse_json_object
from .prompts import NEWS_SYSTEM_PROMPT

_TAVILY_URL = "https://api.tavily.com/search"


class NewsService:
    def __init__(self, client: Any, config: Config,
                 http_post: Callable = requests.post,
                 now: Callable[[], float] = time.time):
        self._client = client
        self._cfg = config
        self._post = http_post
        self._now = now
        self._cache: dict[str, tuple[float, Optional[dict]]] = {}

    def report(self, pair: str) -> tuple[Optional[dict], bool]:
        """Return (structured news report dict, available). Cached per pair."""
        cached = self._cache.get(pair)
        if cached and (self._now() - cached[0]) < self._cfg.news_cache_ttl:
            return cached[1], cached[1] is not None

        try:
            items = self._fetch(pair)
            rep = self._analyze(pair, items)
            self._cache[pair] = (self._now(), rep)
            return rep, True
        except Exception:  # noqa: BLE001 — news is optional; degrade gracefully
            self._cache[pair] = (self._now(), None)
            return None, False

    def report_or_none(self, pair: str) -> Optional[dict]:
        """Convenience for use as an analyzer news_provider callable."""
        report, _ = self.report(pair)
        return report

    def _fetch(self, pair: str) -> list[dict]:
        base, _, quote = pair.partition("/")
        query = f"{base} {quote} forex news today".strip()
        resp = self._post(
            _TAVILY_URL,
            json={"api_key": self._cfg.tavily_api_key, "query": query,
                  "topic": "news", "days": 2, "max_results": 5},
            timeout=15,
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])
        items = []
        for r in results:
            url = r.get("url", "")
            items.append({
                "title": r.get("title", ""),
                "content": r.get("content", ""),
                "url": url,
                "published_date": r.get("published_date"),
                "source": urlparse(url).netloc or None,
            })
        return items

    def _analyze(self, pair: str, items: list[dict]) -> dict:
        base, _, quote = pair.partition("/")
        payload = {
            "pair": pair,
            "base_currency": base,
            "quote_currency": quote,
            "current_utc_time": datetime.now(timezone.utc).isoformat(),
            "tavily_results": items,
        }
        resp = create_json(
            self._client, self._cfg.news_model,
            [
                {"role": "system", "content": NEWS_SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(payload)},
            ],
            temperature=0.2, max_tokens=1500,
        )
        return parse_json_object(resp.choices[0].message.content)
