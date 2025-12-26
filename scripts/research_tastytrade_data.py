#!/usr/bin/env python3
# type: ignore
# mypy: ignore-errors
"""
Tastytrade Data Research Script

Explores what data we can get from Tastytrade API to reduce yfinance dependency.

Tests:
1. REST API endpoints (quotes, candles, market data)
2. DXLink/DXFeed streaming (if available)
3. Account-based data endpoints
4. Compares Tastytrade vs yfinance capabilities

Usage:
    source .env.tastytrade
    python scripts/research_tastytrade_data.py
    python scripts/research_tastytrade_data.py --symbols SPY AAPL /ES
    python scripts/research_tastytrade_data.py --test-streaming
    python scripts/research_tastytrade_data.py --json
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta
from typing import Any, Optional

try:
    import requests
except ModuleNotFoundError:
    print("ERROR: requests not installed. Run: pip install requests")
    sys.exit(1)

DEFAULT_TEST_SYMBOLS = ["SPY", "AAPL", "/ES"]


class TastytradeResearchClient:
    """Research client for exploring Tastytrade API capabilities."""

    def __init__(self):
        """Initialize with OAuth credentials from environment."""
        self.client_id = os.getenv("TT_CLIENT_ID")
        self.client_secret = os.getenv("TT_CLIENT_SECRET")
        self.refresh_token = os.getenv("TT_REFRESH_TOKEN")
        self.api_base = os.getenv("API_BASE_URL", "https://api.tastytrade.com")

        if not self.client_id or not self.client_secret or not self.refresh_token:
            raise ValueError(
                "Missing Tastytrade credentials. Source .env.tastytrade first:\n"
                "  source .env.tastytrade"
            )

        self._access_token: Optional[str] = None
        self._token_expiry: float = 0.0
        self._session_token: Optional[str] = None

    def _refresh_access_token(self) -> None:
        """Refresh OAuth access token."""
        url = f"{self.api_base}/oauth/token"
        payload = {
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }

        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()

        data = response.json()
        self._access_token = data["access_token"]
        expires_in = data.get("expires_in", 3600)
        self._token_expiry = time.time() + expires_in - 60

        print(f"✅ OAuth token obtained (expires in {expires_in}s)")

    def _get_token(self) -> str:
        """Get valid access token, refreshing if needed."""
        if not self._access_token or time.time() >= self._token_expiry:
            self._refresh_access_token()
        return self._access_token

    def _make_request(
        self, method: str, endpoint: str, params: dict = None, json_data: dict = None
    ) -> Optional[dict]:
        """Make authenticated API request."""
        token = self._get_token()
        url = f"{self.api_base}{endpoint}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }

        try:
            if method == "GET":
                response = requests.get(url, headers=headers, params=params, timeout=15)
            elif method == "POST":
                response = requests.post(url, headers=headers, json=json_data, timeout=15)
            else:
                raise ValueError(f"Unsupported method: {method}")

            # Handle auth retry
            if response.status_code == 401:
                self._access_token = None
                token = self._get_token()
                headers["Authorization"] = f"Bearer {token}"
                if method == "GET":
                    response = requests.get(url, headers=headers, params=params, timeout=15)
                else:
                    response = requests.post(url, headers=headers, json=json_data, timeout=15)

            response.raise_for_status()
            return response.json()

        except requests.exceptions.RequestException as e:
            print(f"❌ API request failed: {e}")
            return None

    def test_market_metrics(self, symbols: list[str]) -> dict[str, Any]:
        """Test /market-metrics endpoint (what we currently use)."""
        print(f"\n{'=' * 80}")
        print("TEST 1: /market-metrics (Current Implementation)")
        print(f"{'=' * 80}")

        symbols_str = ",".join(symbols)
        data = self._make_request("GET", "/market-metrics", params={"symbols": symbols_str})

        if not data:
            return {"success": False, "error": "Request failed"}

        items = data.get("data", {}).get("items", [])
        results = {}

        for item in items:
            symbol = item.get("symbol", "").upper()
            if not symbol:
                continue

            results[symbol] = {
                "iv": item.get("implied-volatility-index"),
                "iv_rank": item.get("implied-volatility-index-rank"),
                "iv_percentile": item.get("implied-volatility-percentile"),
                "hv30": item.get("historical-volatility-30-day"),
                "hv90": item.get("historical-volatility-90-day"),
                "liquidity_rating": item.get("liquidity-rating"),
                "beta": item.get("beta"),
                "corr_spy_3m": item.get("corr-spy-3month"),
                "earnings_date": item.get("earnings", {}).get("expected-report-date"),
            }

            print(f"\n📊 {symbol}:")
            print(f"   IV: {results[symbol]['iv']}")
            print(f"   HV30: {results[symbol]['hv30']}")
            print(f"   HV90: {results[symbol]['hv90']}")
            print(f"   IV Percentile: {results[symbol]['iv_percentile']}")
            print(f"   Liquidity: {results[symbol]['liquidity_rating']}")
            print("   ⚠️  NO PRICE DATA in this endpoint")

        return {"success": True, "data": results}

    def test_quote_endpoint(self, symbols: list[str]) -> dict[str, Any]:
        """Test various quote/price endpoints."""
        print(f"\n{'=' * 80}")
        print("TEST 2: Quote/Price Data Endpoints")
        print(f"{'=' * 80}")

        results = {}

        for symbol in symbols:
            print(f"\n📊 Testing {symbol}")

            # Try multiple endpoint patterns
            patterns_to_try = [
                # Pattern 1: Direct instruments endpoint
                f"/instruments/equities/{symbol}",
                # Pattern 2: Symbols endpoint
                f"/symbols/{symbol}",
                # Pattern 3: Quote endpoint
                f"/quote/{symbol}",
                # Pattern 4: Market data quote
                f"/market-data/quotes/{symbol}",
                # Pattern 5: Greeks endpoint (sometimes has price)
                f"/option-chains/{symbol}/nested",
            ]

            found = False
            for pattern in patterns_to_try:
                data = self._make_request("GET", pattern)
                if data and isinstance(data, dict):
                    # Check if we got price data
                    extracted_data = data.get("data", data)

                    # Look for price fields
                    price_fields = {
                        "last": extracted_data.get("last"),
                        "close": extracted_data.get("close"),
                        "bid": extracted_data.get("bid"),
                        "ask": extracted_data.get("ask"),
                        "mark": extracted_data.get("mark"),
                        "price": extracted_data.get("price"),
                        "underlying_price": extracted_data.get("underlying-price"),
                    }

                    # Filter out None values
                    price_data = {k: v for k, v in price_fields.items() if v is not None}

                    if price_data:
                        print(f"   ✅ Found price data at {pattern}:")
                        for key, val in price_data.items():
                            print(f"      {key}: {val}")
                        results[symbol] = {
                            "endpoint": pattern,
                            "success": True,
                            "price_data": price_data,
                            "all_keys": list(extracted_data.keys())[:15],
                        }
                        found = True
                        break

            if not found:
                results[symbol] = {"success": False}
                print(f"   ❌ No price data found in {len(patterns_to_try)} endpoints")

        return {"success": any(r.get("success") for r in results.values()), "data": results}

    def test_candles_endpoint(self, symbols: list[str]) -> dict[str, Any]:
        """Test candles/OHLCV historical data endpoint."""
        print(f"\n{'=' * 80}")
        print("TEST 3: Historical Candles (OHLCV Data)")
        print(f"{'=' * 80}")

        results = {}

        # Test different time ranges
        end_date = datetime.now()
        start_date = end_date - timedelta(days=365)

        for symbol in symbols:
            print(f"\n📊 Testing {symbol}")

            # Try different endpoint patterns
            endpoints_to_try = [
                f"/market-data/candles/{symbol}",
                f"/instruments/candles/{symbol}",
                f"/market-data/{symbol}/candles",
            ]

            success = False
            for endpoint in endpoints_to_try:
                params = {
                    "start-time": start_date.strftime("%Y-%m-%d"),
                    "end-time": end_date.strftime("%Y-%m-%d"),
                }

                data = self._make_request("GET", endpoint, params=params)
                if data:
                    candles = data.get("data", [])
                    if candles:
                        results[symbol] = {
                            "endpoint": endpoint,
                            "success": True,
                            "candle_count": len(candles),
                            "sample_candle": candles[0] if candles else None,
                        }
                        print(f"   ✅ Found {len(candles)} candles at {endpoint}")
                        print(f"      Sample: {candles[0]}")
                        success = True
                        break

            if not success:
                results[symbol] = {"success": False, "error": "No candles endpoint found"}
                print("   ❌ No historical candles available")

        return {"success": True, "data": results}

    def test_dxlink_streaming(self, symbols: list[str]) -> dict[str, Any]:
        """Test DXLink/DXFeed streaming data (WebSocket)."""
        print(f"\n{'=' * 80}")
        print("TEST 4: DXLink Streaming (WebSocket)")
        print(f"{'=' * 80}")

        # First, try to get DXLink token
        print("\n🔍 Attempting to obtain DXLink token...")

        # Common DXLink endpoint patterns to try
        dxlink_endpoints = [
            "/dxlink-tokens",
            "/api/dxlink-tokens",
            "/quote-streamer-tokens",
            "/sessions",
        ]

        dxlink_token = None
        websocket_url = None

        for endpoint in dxlink_endpoints:
            print(f"   Trying {endpoint}...")
            data = self._make_request("POST", endpoint, json_data={})
            if data:
                print(f"   ✅ Response from {endpoint}: {data}")
                # Look for token or websocket URL in response
                if isinstance(data, dict):
                    dxlink_token = (
                        data.get("token")
                        or data.get("data", {}).get("token")
                        or data.get("streamer-token")
                    )
                    websocket_url = (
                        data.get("websocket-url")
                        or data.get("data", {}).get("websocket-url")
                        or data.get("dxlink-url")
                    )
                    if dxlink_token or websocket_url:
                        break

        if not dxlink_token and not websocket_url:
            print("   ❌ Could not obtain DXLink streaming credentials")
            return {
                "success": False,
                "error": "DXLink streaming not available or requires different auth",
                "note": "May need account-level access or different endpoint",
            }

        print(f"   ✅ DXLink Token: {dxlink_token[:20]}..." if dxlink_token else "")
        print(f"   ✅ WebSocket URL: {websocket_url}" if websocket_url else "")

        # TODO: Implement WebSocket connection if we get credentials
        return {
            "success": True,
            "token_obtained": dxlink_token is not None,
            "websocket_url": websocket_url,
            "note": "WebSocket implementation needed - this is just auth check",
        }

    def test_accounts_endpoint(self) -> dict[str, Any]:
        """Test accounts endpoint to see if we can get account-based streaming."""
        print(f"\n{'=' * 80}")
        print("TEST 5: Accounts & Sessions (Alternative Streaming)")
        print(f"{'=' * 80}")

        # Try to get accounts
        print("\n🔍 Checking accounts endpoint...")
        data = self._make_request("GET", "/customers/me/accounts")

        if not data:
            return {"success": False, "error": "No account data"}

        accounts = data.get("data", {}).get("items", [])
        if not accounts:
            return {"success": False, "error": "No accounts found"}

        print(f"   ✅ Found {len(accounts)} account(s)")
        for account in accounts:
            account_number = account.get("account", {}).get("account-number")
            print(f"      Account: {account_number}")

        # Try to create a quote streaming session
        if accounts:
            account_number = accounts[0].get("account", {}).get("account-number")
            print(f"\n🔍 Attempting to create streaming session for {account_number}...")

            session_data = self._make_request(
                "POST",
                f"/accounts/{account_number}/quote-streamer-tokens",
                json_data={},
            )

            if session_data:
                print(f"   ✅ Streaming token response: {session_data}")
                return {"success": True, "streaming_available": True, "data": session_data}

        return {"success": False, "error": "Could not establish streaming session"}


def print_summary(results: dict[str, Any]) -> None:
    """Print summary of what Tastytrade can provide."""
    print(f"\n{'=' * 80}")
    print("SUMMARY: Tastytrade API Data Availability")
    print(f"{'=' * 80}")

    print("\n✅ AVAILABLE FROM TASTYTRADE:")
    print("   • IV (Implied Volatility)")
    print("   • IV Rank & IV Percentile")
    print("   • HV30 & HV90 (Historical Volatility)")
    print("   • Liquidity ratings")
    print("   • Beta & SPY correlation")
    print("   • Earnings dates")

    if results.get("quotes", {}).get("success"):
        print("   • Real-time quotes (bid/ask/last/mark)")
        print("   • Daily OHLC data")
        print("   • Volume data")
    else:
        print("\n⚠️  QUOTES/PRICES:")
        print("   • Quote endpoint exists but may need different auth")
        print("   • Testing showed mixed results")

    if results.get("candles", {}).get("success"):
        print("\n✅ HISTORICAL DATA:")
        print("   • OHLCV candles available")
        print("   • Can replace yfinance for price history")
    else:
        print("\n❌ HISTORICAL DATA:")
        print("   • Candles endpoint not found or requires different auth")

    if results.get("streaming", {}).get("success"):
        print("\n✅ STREAMING DATA:")
        print("   • DXLink/WebSocket available")
        print("   • Real-time price updates possible")
    else:
        print("\n❌ STREAMING DATA:")
        print("   • DXLink credentials not obtainable with current auth")
        print("   • May require account-level or different subscription")

    print("\n❌ STILL NEED YFINANCE FOR:")
    if not results.get("quotes", {}).get("success"):
        print("   • Current price data (if quotes endpoint unavailable)")
    if not results.get("candles", {}).get("success"):
        print("   • Historical OHLCV data (if candles unavailable)")
        print("   • HV calculations (HV20, HV252)")
    print("   • Options chains (if not in market-metrics)")
    print("   • Sector/industry classification")
    print("   • Fundamental data")

    print("\n📊 RECOMMENDATION:")
    if results.get("quotes", {}).get("success") and results.get("candles", {}).get("success"):
        print("   ✅ Tastytrade can replace yfinance for most data")
        print("   • Implement Tastytrade-first architecture")
        print("   • Fall back to yfinance only for missing data")
    elif results.get("quotes", {}).get("success"):
        print("   ⚠️  Tastytrade can provide real-time prices")
        print("   • Use for current quotes to reduce yfinance API calls")
        print("   • Still need yfinance for historical data")
    else:
        print("   ❌ Tastytrade data access limited with current credentials")
        print("   • Continue using market-metrics endpoint (IV, HV, liquidity)")
        print("   • Rely on yfinance for price data")
        print("   • Consider upgrading Tastytrade subscription for more data access")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Research what data we can get from Tastytrade API"
    )
    parser.add_argument(
        "--symbols",
        nargs="+",
        default=DEFAULT_TEST_SYMBOLS,
        help="Symbols to test (default: SPY AAPL /ES)",
    )
    parser.add_argument(
        "--test-streaming",
        action="store_true",
        help="Test DXLink streaming (may fail without proper subscription)",
    )
    parser.add_argument("--json", action="store_true", help="Output results as JSON")

    args = parser.parse_args()

    try:
        client = TastytradeResearchClient()
    except ValueError as e:
        print(f"❌ {e}")
        sys.exit(1)

    print("\n╔════════════════════════════════════════════════════════════════╗")
    print("║  TASTYTRADE API DATA RESEARCH                                  ║")
    print("║  Exploring alternatives to yfinance                            ║")
    print("╚════════════════════════════════════════════════════════════════╝")
    print(f"\nTesting with symbols: {', '.join(args.symbols)}")

    results = {}

    # Test 1: Market Metrics (current implementation)
    results["market_metrics"] = client.test_market_metrics(args.symbols)

    # Test 2: Quote endpoint (price data)
    results["quotes"] = client.test_quote_endpoint(args.symbols)

    # Test 3: Historical candles
    results["candles"] = client.test_candles_endpoint(args.symbols)

    # Test 4: DXLink streaming (optional)
    if args.test_streaming:
        results["streaming"] = client.test_dxlink_streaming(args.symbols)
        results["accounts"] = client.test_accounts_endpoint()

    if args.json:
        print("\n" + json.dumps(results, indent=2))
    else:
        print_summary(results)

    print("\n✅ Research complete!")
    print("\nNext steps:")
    print("  1. Review summary above")
    print("  2. If quotes/candles work → implement Tastytrade-first provider")
    print("  3. If streaming works → consider real-time updates")
    print("  4. Update HANDOFF.md with findings")


if __name__ == "__main__":
    main()
