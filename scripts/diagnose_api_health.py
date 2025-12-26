#!/usr/bin/env python3
# type: ignore
# mypy: ignore-errors
"""
API Health Diagnostic Tool

Diagnoses connectivity and rate limiting issues with yfinance and Tastytrade APIs.
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

        socket.gethostbyname("query2.finance.yahoo.com")
        print("✅ DNS resolution: OK")
        results["dns"] = "OK"
    except Exception as e:
        print(f"❌ DNS resolution: FAILED - {e}")
        results["dns"] = f"FAILED: {e}"

    # Test HTTP connectivity to Yahoo Finance
    try:
        import requests

        response = requests.head("https://query2.finance.yahoo.com", timeout=5)
        print(f"✅ Yahoo Finance reachable: HTTP {response.status_code}")
        results["yahoo_http"] = response.status_code

        # Check for rate limiting
        if response.status_code == 429:
            print("⚠️  WARNING: Rate limit detected (HTTP 429)")
            retry_after = response.headers.get("Retry-After", "unknown")
            print(f"   Retry-After: {retry_after}")
            results["rate_limited"] = True
            results["retry_after"] = retry_after
        else:
            results["rate_limited"] = False
    except requests.exceptions.Timeout:
        print("❌ Yahoo Finance: TIMEOUT")
        results["yahoo_http"] = "TIMEOUT"
    except Exception as e:
        print(f"❌ Yahoo Finance: FAILED - {e}")
        results["yahoo_http"] = f"FAILED: {e}"

    # Test Tastytrade API
    try:
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
        print("⚠️  Tastytrade credentials: Missing (will use yfinance only)")
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
        import yfinance

        print(f"✅ yfinance version: {yfinance.__version__}")
        results["yfinance_version"] = yfinance.__version__
    except Exception as e:
        print(f"❌ yfinance: {e}")
        results["yfinance_version"] = f"ERROR: {e}"

    try:
        import requests

        print(f"✅ requests version: {requests.__version__}")
        results["requests_version"] = requests.__version__
    except Exception as e:
        print(f"❌ requests: {e}")
        results["requests_version"] = f"ERROR: {e}"

    # Check market hours
    try:
        from variance.get_market_data import is_market_open

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


def test_yfinance_fetch(symbol: str, verbose: bool = False) -> dict[str, Any]:
    """Test fetching data for a single symbol via yfinance."""
    result = {"symbol": symbol, "success": False, "errors": [], "data": {}}

    try:
        import yfinance as yf

        ticker = yf.Ticker(symbol)

        # Test 1: Basic info
        try:
            info = ticker.info
            if info:
                result["data"]["info"] = "Available"
                if verbose:
                    print(f"   Info keys: {list(info.keys())[:5]}...")
            else:
                result["errors"].append("Info empty")
        except Exception as e:
            result["errors"].append(f"Info failed: {e}")

        # Test 2: Price data
        try:
            price = ticker.history(period="1d")
            if not price.empty:
                last_close = price["Close"].iloc[-1]
                result["data"]["price"] = float(last_close)
                if verbose:
                    print(f"   Price: ${last_close:.2f}")
            else:
                result["errors"].append("Price history empty")
        except Exception as e:
            result["errors"].append(f"Price fetch failed: {e}")

        # Test 3: Historical data (1 year)
        try:
            hist = ticker.history(period="1y")
            if not hist.empty:
                result["data"]["history_rows"] = len(hist)
                if verbose:
                    print(f"   History: {len(hist)} rows")
            else:
                result["errors"].append("History empty (1y)")
        except Exception as e:
            result["errors"].append(f"History fetch failed: {e}")

        # Test 4: Options (if equity)
        if not symbol.startswith("/") and not symbol.startswith("^"):
            try:
                options = ticker.options
                if options:
                    result["data"]["options_dates"] = len(options)
                    if verbose:
                        print(f"   Options: {len(options)} expiration dates")
                else:
                    result["errors"].append("No options available")
            except Exception as e:
                result["errors"].append(f"Options fetch failed: {e}")

        # Success if we got any data
        result["success"] = len(result["data"]) > 0

    except Exception as e:
        result["errors"].append(f"yfinance error: {e}")
        result["success"] = False

    return result


def test_tastytrade_fetch(symbol: str) -> dict[str, Any]:
    """Test fetching data via Tastytrade API."""
    result = {"symbol": symbol, "success": False, "errors": [], "data": {}}

    try:
        from variance.tastytrade_client import TastytradeAuthError, TastytradeClient

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

    results = {"yfinance": {}, "tastytrade": {}}

    for symbol in symbols:
        print(f"\n📊 Testing: {symbol}")

        # Test yfinance
        print("   yfinance:")
        yf_result = test_yfinance_fetch(symbol, verbose=verbose)
        if yf_result["success"]:
            print(f"   ✅ yfinance: OK ({len(yf_result['data'])} data points)")
        else:
            print("   ❌ yfinance: FAILED")
            for error in yf_result["errors"]:
                print(f"      - {error}")
        results["yfinance"][symbol] = yf_result

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
    if network.get("rate_limited"):
        print("🔴 ISSUE: Yahoo Finance rate limiting detected")
        print(f"   Retry after: {network.get('retry_after', 'unknown')}")
        print("   Solution: Wait 15-60 minutes before retrying")
    elif network.get("yahoo_http") == "TIMEOUT":
        print("🔴 ISSUE: Network timeout to Yahoo Finance")
        print("   Solution: Check internet connection")
    elif network.get("yahoo_http") not in [200, 301, 302]:
        print(f"🔴 ISSUE: Yahoo Finance API not responding (HTTP {network.get('yahoo_http')})")
    else:
        print("✅ Network: OK")

    # Credentials
    if "Missing" in str(env.get("tastytrade_creds", "")):
        print("⚠️  INFO: Tastytrade credentials missing - using yfinance only")
    else:
        print("✅ Tastytrade: Configured")

    # Market hours
    if env.get("market_open"):
        print("✅ Market: OPEN")
    else:
        print("ℹ️  Market: CLOSED (will use cache if available)")

    # Symbol fetch results
    yf_results = symbols.get("yfinance", {})
    success_count = sum(1 for r in yf_results.values() if r["success"])
    total_count = len(yf_results)

    if success_count == total_count and total_count > 0:
        print(f"✅ Symbol fetching: {success_count}/{total_count} successful")
    elif success_count > 0:
        print(f"⚠️  Symbol fetching: {success_count}/{total_count} successful")
    else:
        print("🔴 ISSUE: Symbol fetching failed for all symbols")
        print("   Common causes:")
        print("   - Rate limiting (wait and retry)")
        print("   - Network connectivity issues")
        print("   - yfinance API degradation")

    # Cache
    if cache.get("cache_found"):
        print(f"✅ Cache: Available ({cache.get('cached_symbols', 0)} symbols)")
    else:
        print("⚠️  Cache: Not found (first run will be slower)")

    # Recommendations
    print("\n📋 RECOMMENDATIONS:")
    if network.get("rate_limited"):
        print("   1. Wait 1 hour before retrying")
        print("   2. Reduce number of symbols in portfolio")
        print("   3. Use cache from previous successful run")
    elif success_count == 0:
        print("   1. Check internet connection")
        print("   2. Try again in 15-30 minutes")
        print("   3. Check if yfinance is experiencing outages")
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
    if network.get("rate_limited"):
        sys.exit(2)  # Rate limited
    elif all(r["success"] for r in symbols.get("yfinance", {}).values()):
        sys.exit(0)  # All good
    else:
        sys.exit(1)  # Some failures


if __name__ == "__main__":
    main()
