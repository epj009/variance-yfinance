#!/usr/bin/env python3
# type: ignore
# mypy: ignore-errors
"""
Comprehensive Verification: Can We Get Positions & Greeks from Tastytrade?

This script definitively answers:
1. Can we fetch account positions via REST API with OAuth?
2. Can we fetch account positions via tastytrade SDK?
3. Can we get Greeks via DXLinkStreamer?
4. What authentication tier do we actually have?

Usage:
    source .env.tastytrade
    python scripts/verify_positions_greeks_access.py
    python scripts/verify_positions_greeks_access.py --try-sdk
"""

import argparse
import os
import sys
import time
from typing import Any, Optional

try:
    import requests
except ModuleNotFoundError:
    print("ERROR: requests not installed. Run: pip install requests")
    sys.exit(1)


class PositionsGreeksVerifier:
    """Verify what account/positions data we can access."""

    def __init__(self):
        """Initialize with OAuth credentials."""
        self.client_id = os.getenv("TT_CLIENT_ID")
        self.client_secret = os.getenv("TT_CLIENT_SECRET")
        self.refresh_token = os.getenv("TT_REFRESH_TOKEN")
        self.api_base = os.getenv("API_BASE_URL", "https://api.tastytrade.com")

        if not all([self.client_id, self.client_secret, self.refresh_token]):
            raise ValueError("Missing Tastytrade credentials. Source .env.tastytrade first")

        self._access_token: Optional[str] = None
        self._token_expiry: float = 0.0

    def _refresh_oauth_token(self) -> None:
        """Refresh OAuth access token."""
        url = f"{self.api_base}/oauth/token"
        payload = {
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }

        print("🔐 Refreshing OAuth token...")
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()

        data = response.json()
        self._access_token = data["access_token"]
        expires_in = data.get("expires_in", 3600)
        self._token_expiry = time.time() + expires_in - 60

        print(f"   ✅ OAuth token obtained (expires in {expires_in}s)")
        print(f"   Token (first 20 chars): {self._access_token[:20]}...")

    def _get_token(self) -> str:
        """Get valid OAuth token."""
        if not self._access_token or time.time() >= self._token_expiry:
            self._refresh_oauth_token()
        return self._access_token

    def _request(self, method: str, endpoint: str, **kwargs) -> tuple[Optional[dict], int, str]:
        """
        Make authenticated request and return (data, status_code, error_msg).

        Returns:
            Tuple of (response_dict, status_code, error_message)
        """
        token = self._get_token()
        url = f"{self.api_base}{endpoint}"
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

        try:
            if method == "GET":
                response = requests.get(url, headers=headers, timeout=15, **kwargs)
            elif method == "POST":
                response = requests.post(url, headers=headers, timeout=15, **kwargs)
            else:
                return None, 0, f"Unsupported method: {method}"

            # Return regardless of status
            try:
                data = response.json()
            except Exception:
                data = {"raw_text": response.text[:200]}

            return data, response.status_code, response.reason

        except requests.exceptions.Timeout:
            return None, 0, "Request timeout"
        except requests.exceptions.RequestException as e:
            return None, 0, str(e)

    def test_1_account_endpoints(self) -> dict[str, Any]:
        """Test if we can access account information."""
        print("\n" + "=" * 80)
        print("TEST 1: Account Access (Prerequisite for Positions)")
        print("=" * 80)

        endpoints_to_test = [
            "/customers/me",
            "/customers/me/accounts",
            "/accounts",
        ]

        results = {}

        for endpoint in endpoints_to_test:
            print(f"\n📍 Testing: {endpoint}")
            data, status, reason = self._request("GET", endpoint)

            result = {
                "endpoint": endpoint,
                "status_code": status,
                "reason": reason,
                "accessible": status == 200,
            }

            if status == 200 and data:
                print("   ✅ SUCCESS (200 OK)")
                result["data_sample"] = {
                    "keys": list(data.keys())[:10] if isinstance(data, dict) else None,
                    "has_accounts": "accounts" in str(data).lower(),
                }
                if isinstance(data, dict):
                    # Try to extract account numbers
                    accounts_data = data.get("data", {})
                    if isinstance(accounts_data, dict):
                        items = accounts_data.get("items", [])
                        if items:
                            print(f"   📊 Found {len(items)} account(s)")
                            result["account_count"] = len(items)
            elif status == 401:
                print("   ❌ UNAUTHORIZED (401) - OAuth token invalid")
            elif status == 403:
                print("   ❌ FORBIDDEN (403) - Insufficient permissions")
                print("      → OAuth credentials don't have account-level access")
            elif status == 404:
                print("   ❌ NOT FOUND (404) - Endpoint doesn't exist")
            elif status == 0:
                print(f"   ❌ TIMEOUT/ERROR - {reason}")
            else:
                print(f"   ⚠️  Status {status}: {reason}")

            if data and status != 200:
                error_msg = data.get("error", {}).get("message") if isinstance(data, dict) else None
                if error_msg:
                    print(f"      Error: {error_msg}")
                    result["error_message"] = error_msg

            results[endpoint] = result

        return results

    def test_2_positions_endpoints(self) -> dict[str, Any]:
        """Test if we can access positions (requires account access first)."""
        print("\n" + "=" * 80)
        print("TEST 2: Positions Endpoints")
        print("=" * 80)

        # First, try to get an account number
        print("\n🔍 Step 1: Attempt to get account number...")
        accounts_data, status, reason = self._request("GET", "/customers/me/accounts")

        account_number = None
        if status == 200 and accounts_data:
            items = accounts_data.get("data", {}).get("items", [])
            if items:
                account_number = items[0].get("account", {}).get("account-number")
                print(f"   ✅ Got account number: {account_number}")
        else:
            print(f"   ❌ Cannot get account number (status {status})")
            print("      Cannot test positions endpoint without account number")

        results = {"account_number_obtained": account_number is not None}

        if not account_number:
            # Try with a placeholder to see the error
            account_number = "PLACEHOLDER"
            print("\n   Using placeholder account number to test endpoint...")

        # Test positions endpoint
        positions_endpoint = f"/accounts/{account_number}/positions"
        print(f"\n📍 Testing: {positions_endpoint}")

        data, status, reason = self._request("GET", positions_endpoint)

        result = {
            "endpoint": positions_endpoint,
            "status_code": status,
            "reason": reason,
            "accessible": status == 200,
        }

        if status == 200 and data:
            print("   ✅ SUCCESS (200 OK)")
            positions = data.get("data", {}).get("items", [])
            print(f"   📊 Found {len(positions)} position(s)")
            result["position_count"] = len(positions)

            if positions:
                # Sample first position structure
                first_pos = positions[0]
                print("\n   Sample position fields:")
                for key in list(first_pos.keys())[:15]:
                    print(f"      • {key}: {first_pos.get(key)}")
                result["sample_fields"] = list(first_pos.keys())
        elif status == 401:
            print("   ❌ UNAUTHORIZED (401)")
        elif status == 403:
            print("   ❌ FORBIDDEN (403) - OAuth doesn't have account access")
        elif status == 404:
            print("   ❌ NOT FOUND (404)")
        else:
            print(f"   ⚠️  Status {status}: {reason}")

        if data and status != 200:
            error_msg = data.get("error", {}).get("message") if isinstance(data, dict) else None
            if error_msg:
                print(f"      Error: {error_msg}")
                result["error_message"] = error_msg

        results["positions"] = result
        return results

    def test_3_dxlink_token(self) -> dict[str, Any]:
        """Test if we can get DXLink streaming token."""
        print("\n" + "=" * 80)
        print("TEST 3: DXLink Streaming Token")
        print("=" * 80)

        endpoints_to_test = [
            ("/api-quote-tokens", "POST", {}),
            ("/quote-streamer-tokens", "POST", {}),
            ("/api/quote-streamer-tokens", "POST", {}),
        ]

        results = {}

        for endpoint, method, payload in endpoints_to_test:
            print(f"\n📍 Testing: {method} {endpoint}")

            if method == "POST":
                data, status, reason = self._request("POST", endpoint, json=payload)
            else:
                data, status, reason = self._request("GET", endpoint)

            result = {
                "endpoint": endpoint,
                "method": method,
                "status_code": status,
                "reason": reason,
                "accessible": status == 200,
            }

            if status == 200 and data:
                print("   ✅ SUCCESS (200 OK)")
                # Look for token/websocket URL
                token = data.get("token") or data.get("data", {}).get("token")
                ws_url = data.get("websocket-url") or data.get("data", {}).get("websocket-url")

                if token:
                    print(f"   🎫 Token obtained: {token[:20]}...")
                    result["token_obtained"] = True
                if ws_url:
                    print(f"   🔗 WebSocket URL: {ws_url}")
                    result["websocket_url"] = ws_url
            elif status == 401:
                print("   ❌ UNAUTHORIZED (401)")
            elif status == 403:
                print("   ❌ FORBIDDEN (403) - OAuth doesn't have streaming access")
            elif status == 404:
                print("   ❌ NOT FOUND (404) - Endpoint doesn't exist")
            else:
                print(f"   ⚠️  Status {status}: {reason}")

            if data and status != 200:
                error_msg = data.get("error", {}).get("message") if isinstance(data, dict) else None
                if error_msg:
                    print(f"      Error: {error_msg}")
                    result["error_message"] = error_msg

            results[endpoint] = result

        return results

    def test_4_sdk_access(self) -> dict[str, Any]:
        """Test if tastytrade SDK can access accounts/positions."""
        print("\n" + "=" * 80)
        print("TEST 4: tastytrade SDK (tastyware) - Account & Positions")
        print("=" * 80)

        try:
            import tastytrade
            from tastytrade import Account, Session
        except ImportError:
            print("   ⚠️  tastytrade SDK not installed")
            print("      Install with: pip install tastytrade")
            return {"sdk_installed": False}

        print(f"   ✅ tastytrade SDK version: {tastytrade.__version__}")

        results = {"sdk_installed": True}

        # Test 1: Create session with OAuth credentials
        print("\n🔐 Step 1: Create Session with OAuth credentials...")
        try:
            # The SDK expects (login, password) OR (client_id, refresh_token)
            # Let's try the OAuth approach
            session = Session(self.client_secret, self.refresh_token)
            print("   ✅ Session created successfully")
            results["session_created"] = True
        except Exception as e:
            print(f"   ❌ Session creation failed: {e}")
            results["session_created"] = False
            results["session_error"] = str(e)
            return results

        # Test 2: Get accounts
        print("\n📋 Step 2: Attempt to get accounts...")
        try:
            accounts = Account.get_accounts(session)
            print(f"   ✅ Got {len(accounts)} account(s)")
            results["accounts_accessible"] = True
            results["account_count"] = len(accounts)

            if accounts:
                account = accounts[0]
                print(f"      Account number: {account.account_number}")
                results["account_number"] = account.account_number
        except Exception as e:
            print(f"   ❌ Failed to get accounts: {e}")
            print(f"      Error type: {type(e).__name__}")
            results["accounts_accessible"] = False
            results["accounts_error"] = str(e)
            return results

        # Test 3: Get positions
        if results.get("accounts_accessible") and accounts:
            print("\n📊 Step 3: Attempt to get positions...")
            try:
                account = accounts[0]
                positions = account.get_positions(session)
                print(f"   ✅ Got {len(positions)} position(s)")
                results["positions_accessible"] = True
                results["position_count"] = len(positions)

                if positions:
                    pos = positions[0]
                    print("\n   Sample position:")
                    print(f"      Symbol: {pos.symbol}")
                    print(f"      Quantity: {pos.quantity}")
                    print(f"      Type: {pos.instrument_type}")
                    # Check if Greeks are in position data
                    print("\n   Checking for Greeks in position object...")
                    has_delta = hasattr(pos, "delta") and pos.delta is not None
                    has_gamma = hasattr(pos, "gamma") and pos.gamma is not None
                    print(f"      Delta: {has_delta}")
                    print(f"      Gamma: {has_gamma}")
                    results["positions_have_greeks"] = has_delta or has_gamma
            except Exception as e:
                print(f"   ❌ Failed to get positions: {e}")
                print(f"      Error type: {type(e).__name__}")
                results["positions_accessible"] = False
                results["positions_error"] = str(e)

        return results

    def test_5_sdk_streamer(self) -> dict[str, Any]:
        """Test if DXLinkStreamer works with SDK."""
        print("\n" + "=" * 80)
        print("TEST 5: DXLinkStreamer (SDK) - Greeks Access")
        print("=" * 80)

        try:
            import asyncio

            from tastytrade import DXLinkStreamer, Session
            from tastytrade.dxfeed import Greeks
        except ImportError as e:
            print(f"   ⚠️  Required imports not available: {e}")
            return {"sdk_installed": False}

        print("   ✅ DXLinkStreamer imports successful")

        results = {"imports_available": True}

        # Test streamer connection
        print("\n🔗 Attempting to create DXLinkStreamer...")

        async def test_streamer():
            try:
                session = Session(self.client_secret, self.refresh_token)
                print("   ✅ Session created")

                # Try to create streamer
                print("   🔗 Creating DXLinkStreamer...")
                async with DXLinkStreamer(session) as streamer:
                    print("   ✅ DXLinkStreamer created successfully!")

                    # Try to subscribe to a test symbol
                    print("   📡 Attempting to subscribe to Greeks for SPY...")
                    test_symbols = ["SPY"]
                    await streamer.subscribe(Greeks, test_symbols)
                    print("   ✅ Subscription successful!")

                    # Try to get one event with timeout
                    print("   ⏳ Waiting for Greeks event (5s timeout)...")
                    try:
                        greeks = await asyncio.wait_for(streamer.get_event(Greeks), timeout=5.0)
                        print("   ✅ Received Greeks event!")
                        print(f"      Symbol: {greeks.eventSymbol}")
                        print(f"      Delta: {greeks.delta}")
                        print(f"      Gamma: {greeks.gamma}")
                        print(f"      Theta: {greeks.theta}")
                        print(f"      Vega: {greeks.vega}")
                        return {
                            "streamer_accessible": True,
                            "greeks_received": True,
                        }
                    except asyncio.TimeoutError:
                        print("   ⚠️  Timeout waiting for Greeks event")
                        return {
                            "streamer_accessible": True,
                            "greeks_received": False,
                            "note": "Subscription worked but no data received",
                        }

            except Exception as e:
                print(f"   ❌ Streamer test failed: {e}")
                print(f"      Error type: {type(e).__name__}")
                return {"streamer_accessible": False, "error": str(e)}

        # Run async test
        try:
            loop_results = asyncio.run(test_streamer())
            results.update(loop_results)
        except Exception as e:
            print(f"   ❌ Async execution failed: {e}")
            results["async_error"] = str(e)

        return results


def print_final_verdict(all_results: dict[str, Any]) -> None:
    """Print the final verdict on what's possible."""
    print("\n" + "=" * 80)
    print("FINAL VERDICT: What Can We Access?")
    print("=" * 80)

    print("\n1️⃣  ACCOUNT ACCESS (via REST API):")
    acct_results = all_results.get("test_1", {})
    any_success = any(r.get("accessible") for r in acct_results.values())
    if any_success:
        print("   ✅ CAN access account endpoints")
    else:
        print("   ❌ CANNOT access account endpoints with OAuth credentials")
        print("      → OAuth tier doesn't include account-level permissions")

    print("\n2️⃣  POSITIONS ACCESS (via REST API):")
    pos_results = all_results.get("test_2", {})
    if pos_results.get("account_number_obtained"):
        pos_accessible = pos_results.get("positions", {}).get("accessible")
        if pos_accessible:
            print("   ✅ CAN access positions endpoint")
            print(
                f"      → Found {pos_results.get('positions', {}).get('position_count', 0)} positions"
            )
        else:
            print("   ❌ CANNOT access positions endpoint")
    else:
        print("   ❌ CANNOT access positions (no account access)")

    print("\n3️⃣  DXLINK STREAMING TOKEN (for Greeks):")
    dxlink_results = all_results.get("test_3", {})
    any_token = any(r.get("token_obtained") for r in dxlink_results.values())
    if any_token:
        print("   ✅ CAN obtain DXLink streaming token")
    else:
        print("   ❌ CANNOT obtain DXLink streaming token")
        print("      → Required for real-time Greeks via WebSocket")

    print("\n4️⃣  TASTYTRADE SDK ACCESS:")
    sdk_results = all_results.get("test_4", {})
    if not sdk_results.get("sdk_installed"):
        print("   ⚠️  SDK not installed (cannot test)")
    elif sdk_results.get("positions_accessible"):
        print("   ✅ SDK CAN access positions")
        print(f"      → Found {sdk_results.get('position_count', 0)} positions")
        if sdk_results.get("positions_have_greeks"):
            print("   ✅ Positions include Greeks data!")
        else:
            print("   ⚠️  Positions DO NOT include Greeks")
    else:
        print("   ❌ SDK CANNOT access positions")
        if sdk_results.get("accounts_error"):
            print(f"      Error: {sdk_results['accounts_error'][:100]}")

    print("\n5️⃣  DXLINKSTREAMER (SDK):")
    streamer_results = all_results.get("test_5", {})
    if not streamer_results.get("imports_available"):
        print("   ⚠️  SDK not installed (cannot test)")
    elif streamer_results.get("greeks_received"):
        print("   ✅ DXLinkStreamer WORKS - Greeks received!")
    elif streamer_results.get("streamer_accessible"):
        print("   ⚠️  Streamer connects but no Greeks data received")
    else:
        print("   ❌ DXLinkStreamer DOES NOT WORK")
        if streamer_results.get("error"):
            print(f"      Error: {streamer_results['error'][:100]}")

    print("\n" + "=" * 80)
    print("CONCLUSION:")
    print("=" * 80)

    # Determine if positions + Greeks are possible
    positions_via_rest = pos_results.get("positions", {}).get("accessible", False)
    positions_via_sdk = sdk_results.get("positions_accessible", False)
    greeks_via_streamer = streamer_results.get("greeks_received", False)

    if positions_via_sdk and greeks_via_streamer:
        print("\n✅ YES - You CAN implement RFC-006 Broker Bridge!")
        print("   • Positions accessible via tastytrade SDK")
        print("   • Greeks accessible via DXLinkStreamer")
        print("   • Previous research may have used wrong auth method")
    elif positions_via_rest:
        print("\n⚠️  PARTIAL - Positions YES, Greeks MAYBE")
        print("   • Positions accessible via REST API")
        if greeks_via_streamer:
            print("   • Greeks accessible via DXLinkStreamer")
        else:
            print("   • Greeks NOT tested or failed")
    else:
        print("\n❌ NO - Cannot implement RFC-006 with current credentials")
        print("   • OAuth credentials lack account-level permissions")
        print("   • Previous research findings CONFIRMED")
        print("\nOptions:")
        print("   1. Keep using CSV export (current workflow)")
        print("   2. Upgrade Tastytrade account/subscription for API access")
        print("   3. Use account credentials (username/password) instead of OAuth")


def main():
    parser = argparse.ArgumentParser(description="Verify Tastytrade positions and Greeks access")
    parser.add_argument(
        "--try-sdk",
        action="store_true",
        help="Test tastytrade SDK (requires: pip install tastytrade)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run all tests including SDK and streaming",
    )

    args = parser.parse_args()

    print("\n╔════════════════════════════════════════════════════════════════╗")
    print("║  POSITIONS & GREEKS ACCESS VERIFICATION                       ║")
    print("║  Can we sync positions from Tastytrade API?                   ║")
    print("╚════════════════════════════════════════════════════════════════╝")

    try:
        verifier = PositionsGreeksVerifier()
    except ValueError as e:
        print(f"\n❌ {e}")
        sys.exit(1)

    all_results = {}

    # Always run REST API tests
    all_results["test_1"] = verifier.test_1_account_endpoints()
    all_results["test_2"] = verifier.test_2_positions_endpoints()
    all_results["test_3"] = verifier.test_3_dxlink_token()

    # SDK tests (optional)
    if args.try_sdk or args.all:
        all_results["test_4"] = verifier.test_4_sdk_access()
        all_results["test_5"] = verifier.test_5_sdk_streamer()

    # Print final verdict
    print_final_verdict(all_results)

    print("\n✅ Verification complete!")


if __name__ == "__main__":
    main()
