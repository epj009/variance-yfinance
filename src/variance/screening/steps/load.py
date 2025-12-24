"""
Watchlist Loading Step
"""

import csv
from typing import Any, Dict, List


def load_watchlist(system_config: Dict[str, Any]) -> List[str]:
    """Reads symbols from the configured CSV path."""
    path = system_config.get("watchlist_path", "watchlists/default-watchlist.csv")
    fallback = system_config.get("fallback_symbols", ["SPY", "QQQ", "IWM"])

    symbols = []
    try:
        with open(path) as f:
            reader = csv.reader(f)
            for row in reader:
                if row and row[0] != "Symbol":
                    symbols.append(row[0])
    except FileNotFoundError:
        symbols = fallback
    except Exception:
        symbols = fallback

    return symbols
