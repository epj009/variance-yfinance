"""
Common utilities shared across Variance scripts.

This module provides shared functionality to avoid code duplication:
- Configuration loading
- Sector/Asset class mapping
- Environment warnings
"""
import json
import sys
from typing import Any, Dict, Optional

# Load Market Config (for Asset Class Map)
MARKET_CONFIG: Dict[str, Any] = {}
try:
    with open('config/market_config.json', 'r') as f:
        MARKET_CONFIG = json.load(f)
except FileNotFoundError:
    print("Warning: config/market_config.json not found. Asset class mapping will be limited.", file=sys.stderr)

# Build reverse lookup: sector -> asset class
SECTOR_TO_ASSET_CLASS: Dict[str, str] = {}
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

