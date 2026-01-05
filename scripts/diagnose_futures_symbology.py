#!/usr/bin/env python3
"""
Diagnose DXLink symbology resolution for futures in the watchlist.

Usage:
    python3 scripts/diagnose_futures_symbology.py [watchlist_file]
"""

import os
import sys
from pathlib import Path

# Add project root
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from variance.portfolio_parser import get_root_symbol
from variance.tastytrade import TastytradeClient


def load_env_file(filepath: Path) -> None:
    """Load environment variables."""
    if not filepath.exists():
        return
    with open(filepath) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[7:]
            if "=" in line:
                key, value = line.split("=", 1)
                value = value.strip().strip('"').strip("'")
                os.environ[key.strip()] = value


def load_watchlist(path: Path) -> list[str]:
    symbols: list[str] = []
    with open(path) as f:
        for line in f:
            symbol = line.strip()
            if not symbol or symbol == "Symbol":
                continue
            symbols.append(symbol)
    return symbols


def main() -> int:
    load_env_file(project_root / ".env.tastytrade")

    if len(sys.argv) > 1:
        watchlist_path = Path(sys.argv[1])
    else:
        watchlist_path = project_root / "watchlists" / "default-watchlist.csv"

    if not watchlist_path.exists():
        print(f"❌ Watchlist not found: {watchlist_path}")
        return 1

    symbols = load_watchlist(watchlist_path)
    futures_raw = [s for s in symbols if s.startswith("/")]
    futures_roots = []
    for sym in futures_raw:
        root = get_root_symbol(sym)
        if root:
            futures_roots.append(root)

    futures_roots = list(dict.fromkeys(futures_roots))

    print("=" * 70)
    print("FUTURES DXLink SYMBOLOGY DIAGNOSTIC")
    print("=" * 70)
    print(f"Watchlist: {watchlist_path.name}")
    print(f"Futures roots: {len(futures_roots)}")
    print()

    client = TastytradeClient()

    unresolved = []
    for root in futures_roots:
        resolved = client.resolve_dxlink_symbol(root)
        status = "✅" if resolved else "❌"
        print(f"{status} {root:6} -> {resolved or 'NOT RESOLVED'}")
        if not resolved:
            unresolved.append(root)

    print()
    if unresolved:
        print(f"⚠️  Unresolved futures roots: {', '.join(unresolved)}")
        return 1

    print("✅ All futures roots resolved to DXLink streamer symbols.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
