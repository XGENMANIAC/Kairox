from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

# Module-level limiter so route decorators can reference it at import time.
limiter = Limiter(key_func=get_remote_address)

# slowapi invokes a dynamic-limit provider with no arguments, so the limit
# string lives in module state that create_app() configures from settings.
_analyse_limit_value = "10/minute"


def set_analyse_limit(value: str) -> None:
    global _analyse_limit_value
    _analyse_limit_value = value


def analyse_limit() -> str:
    """Zero-arg limit provider for slowapi; value set by create_app()."""
    return _analyse_limit_value
