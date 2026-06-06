from __future__ import annotations

from .errors import UnknownAssetError, UnsupportedTimeframeError

# Quotes that mark a pair as crypto regardless of the base.
CRYPTO_QUOTES = {"USDT", "USDC", "BUSD", "DAI", "TUSD", "BTC", "ETH", "BNB"}
# Bases that are crypto even when quoted in a fiat currency (e.g. SOL/USD).
CRYPTO_BASES = {
    "BTC", "ETH", "SOL", "XRP", "ADA", "DOGE", "BNB", "LTC", "DOT", "AVAX",
    "MATIC", "LINK", "TRX", "BCH", "XLM", "ATOM", "ETC", "FIL", "APT", "ARB",
}
# Recognized fiat currencies for forex classification.
FIAT = {
    "USD", "EUR", "GBP", "JPY", "CHF", "AUD", "NZD", "CAD",
    "CNH", "SGD", "HKD", "SEK", "NOK", "MXN", "ZAR", "TRY",
}

_BINANCE_TF = {
    "M1": "1m", "M5": "5m", "M15": "15m", "M30": "30m",
    "H1": "1h", "H4": "4h", "D1": "1d", "W1": "1w",
}
_TWELVE_TF = {
    "M1": "1min", "M5": "5min", "M15": "15min", "M30": "30min",
    "H1": "1h", "H4": "4h", "D1": "1day", "W1": "1week",
}


def split_pair(pair: str) -> tuple[str, str]:
    base, _, quote = pair.strip().upper().partition("/")
    return base, quote


def classify(pair: str) -> str:
    base, quote = split_pair(pair)
    if not base or not quote:
        raise UnknownAssetError(f"Cannot parse pair: {pair!r}")
    if quote in CRYPTO_QUOTES or base in CRYPTO_BASES:
        return "crypto"
    if base in FIAT and quote in FIAT:
        return "forex"
    raise UnknownAssetError(f"Cannot classify pair as crypto or forex: {pair!r}")


def to_binance_symbol(pair: str) -> str:
    base, quote = split_pair(pair)
    return f"{base}{quote}"


def to_twelvedata_symbol(pair: str) -> str:
    base, quote = split_pair(pair)
    return f"{base}/{quote}"


def timeframe_to_interval(timeframe: str, provider: str) -> str:
    table = _BINANCE_TF if provider == "binance" else _TWELVE_TF
    tf = timeframe.strip().upper()
    if tf not in table:
        raise UnsupportedTimeframeError(
            f"Unsupported timeframe {timeframe!r}; "
            f"expected one of {sorted(table)}")
    return table[tf]
