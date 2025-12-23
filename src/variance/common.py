"""
Common utilities shared across Variance scripts.

This module provides shared functionality to avoid code duplication:
- Configuration loading
- Sector/Asset class mapping
- Environment warnings
"""
import sys
from typing import Any

# Load Market Config (for Asset Class Map)
from .config_loader import load_market_config

MARKET_CONFIG: dict[str, Any] = load_market_config()

# Build reverse lookup: sector -> asset class
SECTOR_TO_ASSET_CLASS: dict[str, str] = {}
if 'ASSET_CLASS_MAP' in MARKET_CONFIG:
    for asset_class, sectors in MARKET_CONFIG['ASSET_CLASS_MAP'].items():
        for sector in sectors:
            SECTOR_TO_ASSET_CLASS[sector] = asset_class


def warn_if_not_venv() -> None:
    """
    Warn the user if not running in a virtual environment.

    Checks if the current Python interpreter is running in a virtual environment
    and prints a warning message if not.
    """
    if sys.prefix == getattr(sys, "base_prefix", sys.prefix):
        print("Warning: not running in a virtual environment. Create one with `python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt`.", file=sys.stderr)


def map_sector_to_asset_class(sector: str) -> str:
    """
    Maps a sector string to its asset class.

    Args:
        sector: Sector name (e.g., "Technology", "Energy")

    Returns:
        Asset class (e.g., "Equity", "Commodity", "Fixed Income", "FX", "Index")
    """
    return SECTOR_TO_ASSET_CLASS.get(sector, "Equity")  # Default to Equity if unknown


def get_equivalent_exposures(symbol: str) -> set[str]:
    """
    Returns a set of symbols representing the same underlying exposure.

    Treats futures and their ETF proxies as equivalent for concentration risk management.
    Example: '/SI' -> {'/SI', 'SLV'}
    Example: 'SLV' -> {'SLV', '/SI'}

    Args:
        symbol: Symbol to find equivalents for (e.g., '/SI', 'SLV', 'AAPL')

    Returns:
        Set of equivalent symbols including the input symbol
    """
    result = {symbol}
    futures_proxy = MARKET_CONFIG.get('FUTURES_PROXY', {})

    # Forward Lookup (Future -> ETF)
    if symbol in futures_proxy:
        proxy_info = futures_proxy[symbol]
        # Filter on type=='etf' to exclude vol_index proxies
        if proxy_info.get('type') == 'etf':
            if 'iv_symbol' in proxy_info:
                result.add(proxy_info['iv_symbol'])
            if 'hv_symbol' in proxy_info:
                result.add(proxy_info['hv_symbol'])

    # Reverse Lookup (ETF -> Future)
    for fut_symbol, proxy_info in futures_proxy.items():
        # Filter on type=='etf' to exclude vol_index proxies
        if proxy_info.get('type') == 'etf':
            if proxy_info.get('iv_symbol') == symbol or proxy_info.get('hv_symbol') == symbol:
                result.add(fut_symbol)

    return result
