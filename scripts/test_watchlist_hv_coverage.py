#!/usr/bin/env python3
"""
Test HV coverage across full watchlist with DXLink fallback.

Analyzes HV30/HV90 coverage from Tastytrade REST API + DXLink fallback.
Reports which symbols get HV from REST vs DXLink.

Usage:
    python scripts/test_watchlist_hv_coverage.py [watchlist_file]

Defaults to watchlists/default-watchlist.csv if no file specified.
"""

import csv
import os
import sys
from collections import defaultdict
from pathlib import Path

# Add project root
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from variance.market_data.service import MarketDataService


def load_env_file(filepath):
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


# Load Tastytrade credentials
load_env_file(project_root / ".env.tastytrade")

# Enable Tastytrade in runtime config
os.environ["RUNTIME_CONFIG"] = str(project_root / "config" / "runtime_config.json")


def load_watchlist(filepath: Path) -> list[str]:
    """Load symbols from watchlist CSV."""
    symbols: list[str] = []
    with open(filepath) as f:
        rows = list(csv.reader(f))
    if not rows:
        return symbols

    header = [cell.strip().lower() for cell in rows[0]]
    if "symbol" in header:
        idx = header.index("symbol")
        for row in rows[1:]:
            if len(row) <= idx:
                continue
            symbol = row[idx].strip()
            if symbol:
                symbols.append(symbol)
        return symbols

    for row in rows:
        if not row:
            continue
        symbol = row[0].strip()
        if symbol and symbol.lower() != "symbol":
            symbols.append(symbol)
    return symbols


def test_watchlist_coverage(watchlist_path: Path):
    """Test HV coverage across watchlist."""
    print("=" * 70)
    print("WATCHLIST HV COVERAGE TEST - WITH DXLINK FALLBACK")
    print("=" * 70)

    # Load watchlist
    symbols = load_watchlist(watchlist_path)
    print(f"\n1. Loaded {len(symbols)} symbols from {watchlist_path.name}")
    print(f"   First 10: {symbols[:10]}")

    # Create MarketDataService
    print("\n2. Creating MarketDataService with DXLink fallback...")
    service = MarketDataService()

    print("\n3. Fetching market data (this may take a while)...\n")

    # Fetch in batches to avoid overwhelming the system
    batch_size = 10
    all_results = {}

    for i in range(0, len(symbols), batch_size):
        batch = symbols[i : i + batch_size]
        print(f"   Batch {i // batch_size + 1}: {batch[:5]}...")
        batch_results = service.get_market_data(batch)
        all_results.update(batch_results)

    # Analyze coverage
    print("\n" + "=" * 70)
    print("COVERAGE ANALYSIS")
    print("=" * 70)
    print()

    stats = {
        "total": 0,
        "has_hv30": 0,
        "has_hv90": 0,
        "has_both": 0,
        "has_iv": 0,
        "errors": 0,
        "by_source": defaultdict(int),
    }

    missing_hv30 = []
    missing_hv90 = []

    for symbol in symbols:
        data = all_results.get(symbol, {})

        if "error" in data:
            stats["errors"] += 1
            continue

        stats["total"] += 1

        hv30 = data.get("hv30")
        hv90 = data.get("hv90")
        iv = data.get("iv")
        source = data.get("data_source", "unknown")

        stats["by_source"][source] += 1

        if hv30 is not None:
            stats["has_hv30"] += 1
        else:
            missing_hv30.append(symbol)

        if hv90 is not None:
            stats["has_hv90"] += 1
        else:
            missing_hv90.append(symbol)

        if hv30 is not None and hv90 is not None:
            stats["has_both"] += 1

        if iv is not None:
            stats["has_iv"] += 1

    # Calculate percentages
    total = stats["total"]
    if total > 0:
        hv30_pct = stats["has_hv30"] / total * 100
        hv90_pct = stats["has_hv90"] / total * 100
        both_pct = stats["has_both"] / total * 100
        iv_pct = stats["has_iv"] / total * 100
    else:
        hv30_pct = hv90_pct = both_pct = iv_pct = 0

    # Print summary
    print(f"Symbols in watchlist: {len(symbols)}")
    print(f"Successfully processed: {total}")
    print(f"Errors: {stats['errors']}")
    print()
    print(f"HV30 coverage: {stats['has_hv30']}/{total} ({hv30_pct:.1f}%)")
    print(f"HV90 coverage: {stats['has_hv90']}/{total} ({hv90_pct:.1f}%)")
    print(f"Both HV30 & HV90: {stats['has_both']}/{total} ({both_pct:.1f}%)")
    print(f"IV coverage: {stats['has_iv']}/{total} ({iv_pct:.1f}%)")
    print()

    print("Data sources:")
    for source, count in sorted(stats["by_source"].items()):
        pct = count / total * 100 if total > 0 else 0
        print(f"  {source}: {count}/{total} ({pct:.1f}%)")
    print()

    # Show missing symbols
    if missing_hv30 and len(missing_hv30) <= 20:
        print(f"Missing HV30 ({len(missing_hv30)}): {', '.join(missing_hv30)}")
    elif missing_hv30:
        print(f"Missing HV30: {len(missing_hv30)} symbols (>20, not listing)")

    if missing_hv90 and len(missing_hv90) <= 20:
        print(f"Missing HV90 ({len(missing_hv90)}): {', '.join(missing_hv90)}")
    elif missing_hv90:
        print(f"Missing HV90: {len(missing_hv90)} symbols (>20, not listing)")

    # Verdict
    print()
    print("=" * 70)
    print("VERDICT")
    print("=" * 70)
    print()

    if both_pct >= 95:
        print("✅ ✅ ✅  EXCELLENT COVERAGE (>95%)!  ✅ ✅ ✅")
        print()
        print("DXLink fallback is working excellently!")
        print("Nearly all symbols have complete HV metrics.")
        print()
        return True
    elif both_pct >= 80:
        print(f"✅  GOOD COVERAGE ({both_pct:.0f}%)")
        print()
        print("Most symbols have HV metrics.")
        print("This is a significant improvement over REST-only!")
        print()
        return True
    elif both_pct >= 60:
        print(f"⚠️  ACCEPTABLE COVERAGE ({both_pct:.0f}%)")
        print()
        print("Majority of symbols have HV, but room for improvement.")
        print()
        return False
    else:
        print(f"❌  POOR COVERAGE ({both_pct:.0f}%)")
        print()
        print("Many symbols still missing HV metrics.")
        print("Check logs for DXLink errors.")
        print()
        return False


if __name__ == "__main__":
    # Enable detailed logging
    import logging

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )

    # Get watchlist path from args or use default
    if len(sys.argv) > 1:
        watchlist_path = Path(sys.argv[1])
    else:
        watchlist_path = project_root / "watchlists" / "default-watchlist.csv"

    if not watchlist_path.exists():
        print(f"Error: Watchlist not found: {watchlist_path}")
        sys.exit(1)

    success = test_watchlist_coverage(watchlist_path)
    sys.exit(0 if success else 1)
