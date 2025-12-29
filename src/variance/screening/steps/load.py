"""
Watchlist Loading Step
"""

import csv
from typing import Any

from variance.portfolio_parser import get_root_symbol


def load_watchlist(system_config: dict[str, Any]) -> list[str]:
    """
    Reads symbols from the configured CSV path.

    Normalizes futures contract months to root symbols (e.g., /6EH6 -> /6E)
    to ensure compatibility with FUTURES_PROXY configuration.
    """
    path = system_config.get("watchlist_path", "watchlists/default-watchlist.csv")
    fallback = system_config.get("fallback_symbols", ["SPY", "QQQ", "IWM"])

    symbols = []
    try:
        with open(path) as f:
            reader = csv.reader(f)
            for row in reader:
                if row and row[0] != "Symbol":
                    raw_symbol = row[0]
                    # Normalize futures contract months to root symbols
                    normalized = get_root_symbol(raw_symbol)
                    symbols.append(normalized)
    except FileNotFoundError:
        symbols = fallback
    except Exception:
        symbols = fallback

    # Deduplicate while preserving order
    seen = set()
    unique_symbols = []
    for sym in symbols:
        if sym not in seen:
            seen.add(sym)
            unique_symbols.append(sym)

    return unique_symbols
