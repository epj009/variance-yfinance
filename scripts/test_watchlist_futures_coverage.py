#!/usr/bin/env python3
"""
Test futures coverage across the watchlist using PureTastytradeProvider + DXLink.

Usage:
    python3 scripts/test_watchlist_futures_coverage.py [watchlist_file]
"""

import os
import sys
from pathlib import Path

# Add project root
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from variance.market_data.pure_tastytrade_provider import PureTastytradeProvider
from variance.portfolio_parser import get_root_symbol


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
            if not symbol or symbol.lower() == "symbol":
                continue
            symbols.append(symbol)
    return symbols


def main() -> int:
    load_env_file(project_root / ".env.tastytrade")
    os.environ["RUNTIME_CONFIG"] = str(project_root / "config" / "runtime_config.json")

    if len(sys.argv) > 1:
        watchlist_path = Path(sys.argv[1])
    else:
        watchlist_path = project_root / "watchlists" / "default-watchlist.csv"

    if not watchlist_path.exists():
        print(f"❌ Watchlist not found: {watchlist_path}")
        return 1

    symbols = load_watchlist(watchlist_path)
    futures_roots = []
    for sym in symbols:
        if not sym.startswith("/"):
            continue
        root = get_root_symbol(sym)
        if root:
            futures_roots.append(root)

    futures_roots = list(dict.fromkeys(futures_roots))
    if not futures_roots:
        print("No futures found in watchlist.")
        return 0

    print("=" * 70)
    print("WATCHLIST FUTURES COVERAGE TEST")
    print("=" * 70)
    print(f"Watchlist: {watchlist_path.name}")
    print(f"Futures roots: {len(futures_roots)}")
    print(f"Symbols: {futures_roots}")
    print()

    provider = PureTastytradeProvider()
    results = provider.get_market_data(futures_roots)

    ok = 0
    complete = 0
    for symbol in futures_roots:
        data = results.get(symbol, {})
        if "error" in data:
            print(f"❌ {symbol:6} Error: {data['error']}")
            continue

        ok += 1
        has_price = data.get("price") is not None
        has_iv = data.get("iv") is not None
        has_hv30 = data.get("hv30") is not None
        has_hv90 = data.get("hv90") is not None
        has_returns = len(data.get("returns", [])) > 0

        if has_price and has_iv and has_hv30 and has_hv90 and has_returns:
            complete += 1
            status = "✅ COMPLETE"
        elif has_price and has_hv30 and has_hv90:
            status = "✅ GOOD   "
        else:
            status = "⚠️  PARTIAL"

        price = data.get("price")
        iv = data.get("iv")
        hv30 = data.get("hv30")
        hv90 = data.get("hv90")
        returns = len(data.get("returns", []))

        price_str = f"${price:8.2f}" if price is not None else "   None"
        iv_str = f"{iv:5.2f}%" if iv is not None else "  None"
        hv30_str = f"{hv30 * 100:5.2f}%" if hv30 is not None else "  None"
        hv90_str = f"{hv90 * 100:5.2f}%" if hv90 is not None else "  None"

        print(
            f"{status} {symbol:6} "
            f"Price: {price_str} | "
            f"IV: {iv_str} | "
            f"HV30: {hv30_str} | "
            f"HV90: {hv90_str} | "
            f"Returns: {returns:2d}"
        )

    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Total futures: {len(futures_roots)}")
    print(f"Successful: {ok}/{len(futures_roots)}")
    print(f"Complete data: {complete}/{len(futures_roots)}")

    return 0 if ok == len(futures_roots) else 1


if __name__ == "__main__":
    raise SystemExit(main())
