from __future__ import annotations


class UnknownAssetError(ValueError):
    """Pair cannot be classified as crypto or forex."""


class UnsupportedTimeframeError(ValueError):
    """Timeframe is not in the supported set."""


class ForexNotConfiguredError(ValueError):
    """Forex requested but no Twelve Data API key is configured."""


class ProviderError(Exception):
    """An upstream market-data provider failed or returned a bad payload."""
