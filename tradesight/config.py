from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping, Optional

from dotenv import load_dotenv


class ConfigError(Exception):
    """Raised when required configuration is missing."""


DEFAULT_BASE_URL = "https://integrate.api.nvidia.com/v1"
# Google Gemini's OpenAI-compatible endpoint (used if VISION_API_KEY is set
# without an explicit VISION_BASE_URL).
GEMINI_OPENAI_BASE = "https://generativelanguage.googleapis.com/v1beta/openai/"
DEFAULT_VISION_MODEL = "nvidia/nemotron-nano-12b-v2-vl"
DEFAULT_REASONING_MODEL = "moonshotai/kimi-k2.6"
DEFAULT_NEWS_MODEL = "meta/llama-3.3-70b-instruct"


@dataclass
class Config:
    nim_api_key: str
    tavily_api_key: str
    base_url: str = DEFAULT_BASE_URL
    vision_model: str = DEFAULT_VISION_MODEL
    reasoning_model: str = DEFAULT_REASONING_MODEL
    news_model: str = DEFAULT_NEWS_MODEL
    # Vision can run on a different (faster) provider; defaults to NIM.
    vision_base_url: str = DEFAULT_BASE_URL
    vision_api_key: str = ""
    capture_interval: int = 30
    capture_region: str = "full"
    pixel_diff_threshold: float = 2.0
    news_cache_ttl: int = 300
    user_id: str = "local"

    @property
    def vision_on_separate_provider(self) -> bool:
        return (self.vision_base_url != self.base_url
                or self.vision_api_key != self.nim_api_key)

    @classmethod
    def load(cls, env: Optional[Mapping[str, str]] = None) -> "Config":
        if env is None:
            load_dotenv()
            env = os.environ

        nim = env.get("NIM_API_KEY")
        tav = env.get("TAVILY_API_KEY")
        missing = [name for name, val in
                   (("NIM_API_KEY", nim), ("TAVILY_API_KEY", tav)) if not val]
        if missing:
            raise ConfigError(
                "Missing required environment variables: " + ", ".join(missing)
                + ". Copy .env.example to .env and fill them in."
            )

        # Vision provider: if VISION_API_KEY is set, vision uses its own
        # base_url (defaulting to Gemini) + key; otherwise it stays on NIM.
        v_key = (env.get("VISION_API_KEY") or "").strip()
        if v_key:
            vision_api_key = v_key
            vision_base_url = env.get("VISION_BASE_URL") or GEMINI_OPENAI_BASE
        else:
            vision_api_key = nim
            vision_base_url = env.get("VISION_BASE_URL") or DEFAULT_BASE_URL

        return cls(
            nim_api_key=nim,
            tavily_api_key=tav,
            vision_model=env.get("VISION_MODEL", DEFAULT_VISION_MODEL),
            reasoning_model=env.get("REASONING_MODEL", DEFAULT_REASONING_MODEL),
            news_model=env.get("NEWS_MODEL", DEFAULT_NEWS_MODEL),
            vision_base_url=vision_base_url,
            vision_api_key=vision_api_key,
            capture_interval=int(env.get("CAPTURE_INTERVAL", 30)),
            capture_region=env.get("CAPTURE_REGION", "full"),
            pixel_diff_threshold=float(env.get("PIXEL_DIFF_THRESHOLD", 2.0)),
            news_cache_ttl=int(env.get("NEWS_CACHE_TTL", 300)),
        )
