from typing import Optional

from . import settings as md_settings


def map_symbol(raw_symbol: str) -> Optional[str]:
    if not raw_symbol:
        return None
    if raw_symbol in md_settings.SYMBOL_MAP:
        return md_settings.SYMBOL_MAP[raw_symbol]  # type: ignore[no-any-return]
    if raw_symbol.startswith("/"):
        root = raw_symbol[1:3]
        if f"/{root}" in md_settings.SYMBOL_MAP:
            return md_settings.SYMBOL_MAP[f"/{root}"]  # type: ignore[no-any-return]
    return raw_symbol


def is_etf(symbol: str) -> bool:
    if isinstance(symbol, dict):
        return False
    return symbol.upper() in md_settings.ETF_SYMBOLS


def should_skip_earnings(raw_symbol: str, yf_symbol: str) -> bool:
    if isinstance(raw_symbol, dict):
        return True
    if isinstance(yf_symbol, dict):
        return True

    upper = raw_symbol.upper()
    if raw_symbol.startswith("/") or yf_symbol.endswith("=F") or yf_symbol.startswith("^"):
        return True
    return upper in md_settings.SKIP_EARNINGS


__all__ = ["map_symbol", "is_etf", "should_skip_earnings"]
