#!/usr/bin/env python3
# type: ignore
# mypy: ignore-errors
"""
API Health Diagnostic Tool

Diagnoses connectivity and rate limiting issues with Tastytrade APIs.
Helps troubleshoot data fetching failures.

Usage:
    ./scripts/diagnose_api_health.py
    ./scripts/diagnose_api_health.py --symbols SPY AAPL
    ./scripts/diagnose_api_health.py --verbose
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from typing import Any

# Test symbols to check
DEFAULT_TEST_SYMBOLS = ["SPY", "AAPL", "/ES"]


def print_section(title: str) -> None:
    """Print a section header."""
    print(f"\n{'=' * 80}")
    print(f"  {title}")
    print(f"{'=' * 80}")


def test_network_connectivity() -> dict[str, Any]:
    """Test basic network connectivity."""
    print_section("1. NETWORK CONNECTIVITY")

    results = {}

    # Test DNS resolution
    try:
        import socket

        socket.gethostbyname("api.tastytrade.com")
        print("✅ DNS resolution: OK")
        results["dns"] = "OK"
    except Exception as e:
        print(f"❌ DNS resolution: FAILED - {e}")
        results["dns"] = f"FAILED: {e}"

    # Test Tastytrade API
    try:
        import requests

        api_url = os.getenv("API_BASE_URL", "https://api.tastytrade.com")
        response = requests.head(api_url, timeout=5)
        print(f"✅ Tastytrade API reachable: HTTP {response.status_code}")
        results["tastytrade_http"] = response.status_code
    except Exception as e:
        print(f"❌ Tastytrade API: FAILED - {e}")
        results["tastytrade_http"] = f"FAILED: {e}"

    return results


def test_environment() -> dict[str, Any]:
    """Test environment configuration."""
    print_section("2. ENVIRONMENT & CONFIGURATION")

    results = {}

    # Check for Tastytrade credentials
    tt_client_id = os.getenv("TT_CLIENT_ID")
    tt_client_secret = os.getenv("TT_CLIENT_SECRET")
    tt_refresh_token = os.getenv("TT_REFRESH_TOKEN")

    if tt_client_id and tt_client_secret and tt_refresh_token:
        print("✅ Tastytrade credentials: Found")
        results["tastytrade_creds"] = "Found"
    else:
        print("⚠️  Tastytrade credentials: Missing (API calls will fail)")
        missing = []
        if not tt_client_id:
            missing.append("TT_CLIENT_ID")
        if not tt_client_secret:
            missing.append("TT_CLIENT_SECRET")
        if not tt_refresh_token:
            missing.append("TT_REFRESH_TOKEN")
        results["tastytrade_creds"] = f"Missing: {', '.join(missing)}"

    # Check Python version
    import platform

    py_version = platform.python_version()
    print(f"✅ Python version: {py_version}")
    results["python_version"] = py_version

    # Check key dependencies
    try:
        import requests

        print(f"✅ requests version: {requests.__version__}")
        results["requests_version"] = requests.__version__
    except Exception as e:
        print(f"❌ requests: {e}")
        results["requests_version"] = f"ERROR: {e}"

    # Check market hours
    try:
        from variance.market_data.clock import is_market_open

        market_open = is_market_open()
        status = "OPEN" if market_open else "CLOSED"
        print(f"✅ Market status: {status}")
        results["market_open"] = market_open
    except Exception as e:
        print(f"❌ Market status check: {e}")
        results["market_open"] = f"ERROR: {e}"

    # Check current time
    from datetime import datetime

    import pytz

    ny_tz = pytz.timezone("America/New_York")
    now = datetime.now(ny_tz)
    print(f"✅ Current time (ET): {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    results["current_time_et"] = now.strftime("%Y-%m-%d %H:%M:%S %Z")

    return results


def test_tastytrade_fetch(symbol: str) -> dict[str, Any]:
    """Test fetching data via Tastytrade API."""
    result = {"symbol": symbol, "success": False, "errors": [], "data": {}}

    try:
        from variance.tastytrade import TastytradeAuthError, TastytradeClient

        try:
            client = TastytradeClient()
        except TastytradeAuthError as e:
            result["errors"].append(f"Auth failed: {e}")
            return result

        # Fetch metrics
        try:
            metrics = client.get_market_metrics(symbol)
            if metrics:
                result["data"] = {
                    "iv": metrics.get("iv"),
                    "iv_percentile": metrics.get("iv_percentile"),
                    "liquidity_rating": metrics.get("liquidity_rating"),
                }
                result["success"] = True
            else:
                result["errors"].append("Empty response")
        except Exception as e:
            result["errors"].append(f"Fetch failed: {e}")

    except ImportError:
        result["errors"].append("Tastytrade client not available")
    except Exception as e:
        result["errors"].append(f"Unexpected error: {e}")

    return result


def test_symbol_fetch(symbols: list[str], verbose: bool = False) -> dict[str, Any]:
    """Test fetching data for symbols."""
    print_section("3. SYMBOL DATA FETCHING")

    results = {"tastytrade": {}}

    for symbol in symbols:
        print(f"\n📊 Testing: {symbol}")

        # Test Tastytrade
        print("   Tastytrade:")
        tt_result = test_tastytrade_fetch(symbol)
        if tt_result["success"]:
            print("   ✅ Tastytrade: OK")
            if verbose and tt_result["data"]:
                for key, value in tt_result["data"].items():
                    print(f"      {key}: {value}")
        else:
            print(
                f"   ⚠️  Tastytrade: {tt_result['errors'][0] if tt_result['errors'] else 'No data'}"
            )
        results["tastytrade"][symbol] = tt_result

        # Small delay to avoid hammering API
        time.sleep(0.5)

    return results


def test_cache_status() -> dict[str, Any]:
    """Test cache availability and status."""
    print_section("4. CACHE STATUS")

    results = {}

    # Check if cache exists
    cache_paths = [
        ".cache/market_data.db",
        "variance_cache.db",
        os.path.expanduser("~/.variance/cache.db"),
    ]

    cache_found = False
    for path in cache_paths:
        if os.path.exists(path):
            cache_found = True
            size_mb = os.path.getsize(path) / (1024 * 1024)
            print(f"✅ Cache found: {path} ({size_mb:.2f} MB)")
            results["cache_path"] = path
            results["cache_size_mb"] = size_mb

            # Try to read cache
            try:
                import sqlite3

                conn = sqlite3.connect(path)
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM market_data")
                count = cursor.fetchone()[0]
                print(f"   Cached symbols: {count}")
                results["cached_symbols"] = count

                # Get most recent entry
                cursor.execute(
                    "SELECT symbol, timestamp FROM market_data ORDER BY timestamp DESC LIMIT 1"
                )
                recent = cursor.fetchone()
                if recent:
                    print(f"   Most recent: {recent[0]} at {recent[1]}")
                    results["most_recent"] = {"symbol": recent[0], "timestamp": recent[1]}

                conn.close()
            except Exception as e:
                print(f"   ⚠️  Could not read cache: {e}")
                results["cache_read_error"] = str(e)

            break

    if not cache_found:
        print("⚠️  No cache found - first run will be slower")
        results["cache_found"] = False
    else:
        results["cache_found"] = True

    return results


def generate_summary(network: dict, env: dict, symbols: dict, cache: dict) -> None:
    """Generate diagnostic summary."""
    print_section("DIAGNOSTIC SUMMARY")

    # Network issues
    if network.get("tastytrade_http") not in [200, 301, 302]:
        print(f"🔴 ISSUE: Tastytrade API not responding (HTTP {network.get('tastytrade_http')})")
    else:
        print("✅ Network: OK")

    # Credentials
    if "Missing" in str(env.get("tastytrade_creds", "")):
        print("⚠️  INFO: Tastytrade credentials missing - API calls will fail")
    else:
        print("✅ Tastytrade: Configured")

    # Market hours
    if env.get("market_open"):
        print("✅ Market: OPEN")
    else:
        print("ℹ️  Market: CLOSED (will use cache if available)")

    # Symbol fetch results
    tt_results = symbols.get("tastytrade", {})
    success_count = sum(1 for r in tt_results.values() if r["success"])
    total_count = len(tt_results)

    if success_count == total_count and total_count > 0:
        print(f"✅ Symbol fetching: {success_count}/{total_count} successful")
    elif success_count > 0:
        print(f"⚠️  Symbol fetching: {success_count}/{total_count} successful")
    else:
        print("🔴 ISSUE: Symbol fetching failed for all symbols")
        print("   Common causes:")
        print("   - Network connectivity issues")
        print("   - Missing/invalid credentials")

    # Cache
    if cache.get("cache_found"):
        print(f"✅ Cache: Available ({cache.get('cached_symbols', 0)} symbols)")
    else:
        print("⚠️  Cache: Not found (first run will be slower)")

    # Recommendations
    print("\n📋 RECOMMENDATIONS:")
    if success_count == 0:
        print("   1. Check internet connection")
        print("   2. Confirm Tastytrade credentials in `.env.tastytrade`")
        print("   3. Try again in 5-10 minutes")
    elif not cache.get("cache_found"):
        print("   1. Run during market hours to populate cache")
        print("   2. Cache will speed up future runs significantly")
    else:
        print("   ✅ System appears healthy")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Diagnose API health and connectivity issues",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--symbols",
        nargs="+",
        default=DEFAULT_TEST_SYMBOLS,
        help="Symbols to test (default: SPY AAPL /ES)",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed output")
    parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    if not args.json:
        print("╔════════════════════════════════════════════════════════════════╗")
        print("║  VARIANCE API HEALTH DIAGNOSTIC                                ║")
        print("║  Checking connectivity, rate limits, and data availability     ║")
        print("╚════════════════════════════════════════════════════════════════╝")

    # Run diagnostics
    network = test_network_connectivity()
    env = test_environment()
    symbols = test_symbol_fetch(args.symbols, verbose=args.verbose)
    cache = test_cache_status()

    if args.json:
        # JSON output
        output = {
            "timestamp": datetime.now().isoformat(),
            "network": network,
            "environment": env,
            "symbols": symbols,
            "cache": cache,
        }
        print(json.dumps(output, indent=2))
    else:
        # Summary
        generate_summary(network, env, symbols, cache)

    # Exit code
    if all(r["success"] for r in symbols.get("tastytrade", {}).values()):
        sys.exit(0)  # All good
    sys.exit(1)  # Some failures


if __name__ == "__main__":
    main()
