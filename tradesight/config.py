from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping, Optional

from dotenv import load_dotenv


class ConfigError(Exception):
    """Raised when required configuration is missing."""


DEFAULT_VISION_MODEL = "meta/llama-3.2-11b-vision-instruct"
DEFAULT_REASONING_MODEL = "moonshotai/kimi-k2.6"
DEFAULT_NEWS_MODEL = "meta/llama-3.3-70b-instruct"


@dataclass
class Config:
    nim_api_key: str
    tavily_api_key: str
    base_url: str = "https://integrate.api.nvidia.com/v1"
    vision_model: str = DEFAULT_VISION_MODEL
    reasoning_model: str = DEFAULT_REASONING_MODEL
    news_model: str = DEFAULT_NEWS_MODEL
    capture_interval: int = 30
    capture_region: str = "full"
    pixel_diff_threshold: float = 2.0
    news_cache_ttl: int = 300
    user_id: str = "local"

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

        return cls(
            nim_api_key=nim,
            tavily_api_key=tav,
            vision_model=env.get("VISION_MODEL", DEFAULT_VISION_MODEL),
            reasoning_model=env.get("REASONING_MODEL", DEFAULT_REASONING_MODEL),
            news_model=env.get("NEWS_MODEL", DEFAULT_NEWS_MODEL),
            capture_interval=int(env.get("CAPTURE_INTERVAL", 30)),
            capture_region=env.get("CAPTURE_REGION", "full"),
            pixel_diff_threshold=float(env.get("PIXEL_DIFF_THRESHOLD", 2.0)),
            news_cache_ttl=int(env.get("NEWS_CACHE_TTL", 300)),
        )
