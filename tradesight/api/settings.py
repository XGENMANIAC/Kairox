from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict

from tradesight.config import Config, DEFAULT_BASE_URL, GEMINI_OPENAI_BASE


class ApiSettings(BaseSettings):
    """Fail-fast env validation for the web API.

    Required: NIM_API_KEY, TAVILY_API_KEY, GEMINI_API_KEY. Everything else has
    a sensible default. ``to_core_config`` adapts these into the dataclass the
    reused analyzer/news services expect, with vision pinned to Gemini.
    """

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore",
        case_sensitive=False)

    nim_api_key: str
    tavily_api_key: str
    gemini_api_key: str

    vision_model: str = "gemini-2.5-flash"
    vision_base_url: str = GEMINI_OPENAI_BASE
    reasoning_model: str = "moonshotai/kimi-k2.6"
    news_model: str = "meta/llama-3.3-70b-instruct"
    nim_base_url: str = DEFAULT_BASE_URL

    frontend_origin: str = "http://localhost:5173"
    redis_url: str = ""
    twelvedata_api_key: str = ""
    news_cache_ttl: int = 300
    analyse_rate_limit: str = "10/minute"

    def to_core_config(self) -> Config:
        return Config(
            nim_api_key=self.nim_api_key,
            tavily_api_key=self.tavily_api_key,
            base_url=self.nim_base_url,
            vision_model=self.vision_model,
            reasoning_model=self.reasoning_model,
            news_model=self.news_model,
            vision_base_url=self.vision_base_url,
            vision_api_key=self.gemini_api_key,
            news_cache_ttl=self.news_cache_ttl,
        )
