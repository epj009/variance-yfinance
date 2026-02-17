#!/usr/bin/env python3
"""
Diagnose why DXLink streaming is returning 403.

Tests:
1. Account entitlements
2. OAuth scope verification
3. DXLink token endpoint with different auth methods
4. Market data subscriptions status

Usage:
    python scripts/diagnose_dxlink_access.py
"""

import os
import sys
from pathlib import Path

import requests

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))


def load_env_file(filepath):
    """Manually load environment variables from .env file."""
    if not filepath.exists():
        return

    with open(filepath) as f:
        for line in f:
            line = line.strip()
            # Skip comments and empty lines
            if not line or line.startswith("#"):
                continue

            # Handle export statements
            if line.startswith("export "):
                line = line[7:]  # Remove 'export '

            # Parse KEY=VALUE
            if "=" in line:
                key, value = line.split("=", 1)
                # Remove quotes if present
                value = value.strip().strip('"').strip("'")
                os.environ[key.strip()] = value


# Load Tastytrade credentials
load_env_file(project_root / ".env.tastytrade")

TT_BASE = "https://api.tastytrade.com"


def get_oauth_access_token():
    """Get OAuth access token using refresh token grant."""
    client_id = os.getenv("TT_CLIENT_ID")
    client_secret = os.getenv("TT_CLIENT_SECRET")
    refresh_token = os.getenv("TT_REFRESH_TOKEN")

    # Check for missing credentials
    missing = []
    if not client_id:
        missing.append("TT_CLIENT_ID")
    if not client_secret:
        missing.append("TT_CLIENT_SECRET")
    if not refresh_token:
        missing.append("TT_REFRESH_TOKEN")

    if missing:
        print(f"❌ Missing environment variables: {', '.join(missing)}")
        print("\nExpected in .env.tastytrade:")
        print("  export TT_CLIENT_ID=...")
        print("  export TT_CLIENT_SECRET=...")
        print("  export TT_REFRESH_TOKEN=...")
        return None

    print("Attempting OAuth token refresh...")

    response = requests.post(
        f"{TT_BASE}/oauth/token",
        json={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
        },
        timeout=10,
    )

    if response.ok:
        data = response.json()
        token = data["access_token"]
        print(f"✅ OAuth access token obtained: {token[:20]}...")
        return token
    else:
        print(f"❌ OAuth refresh failed: {response.status_code}")
        print(f"Response: {response.text}")
        return None


def check_customer_entitlements(token):
    """Check what entitlements/scopes the account has."""
    print("\n" + "=" * 60)
    print("CUSTOMER ENTITLEMENTS & ACCOUNT INFO")
    print("=" * 60)

    response = requests.get(f"{TT_BASE}/customers/me", headers={"Authorization": f"Bearer {token}"})

    if response.ok:
        data = response.json()["data"]
        print("✅ Customer data retrieved")
        print(f"\nCustomer ID: {data.get('id')}")
        print(f"Email: {data.get('email')}")
        print(f"Account type: {data.get('account-type-name')}")

        # Entitlements
        entitlements = data.get("entitlements", [])
        print(f"\nEntitlements ({len(entitlements)}):")
        if entitlements:
            for ent in entitlements:
                print(f"  - {ent}")
        else:
            print("  (none found)")

        # Agreements
        agreements = data.get("agreements", [])
        print(f"\nAgreements ({len(agreements)}):")
        if agreements:
            for agr in agreements:
                print(f"  - {agr.get('name', 'Unknown')}: {agr.get('signed-date', 'Not signed')}")
        else:
            print("  (none found)")

        # Accounts
        accounts = data.get("accounts", [])
        print(f"\nAccounts ({len(accounts)}):")
        for acc in accounts:
            print(f"  - {acc.get('account-number')}: {acc.get('nickname', 'No nickname')}")

        return data
    else:
        print(f"❌ Failed: {response.status_code}")
        print(f"Response: {response.text}")
        return None


def check_market_data_subscriptions(token, account_number):
    """Check active market data subscriptions."""
    print("\n" + "=" * 60)
    print("MARKET DATA SUBSCRIPTIONS")
    print("=" * 60)

    # Try multiple possible endpoints
    endpoints = [
        f"/accounts/{account_number}/market-data-subscriptions",
        "/customers/me/market-data-subscriptions",
        "/market-data-subscriptions",
    ]

    for endpoint in endpoints:
        print(f"\nTrying: {endpoint}")
        response = requests.get(
            f"{TT_BASE}{endpoint}", headers={"Authorization": f"Bearer {token}"}
        )

        if response.ok:
            subs = response.json().get("data", [])
            print(f"✅ SUCCESS! Active subscriptions: {len(subs)}")
            for sub in subs:
                print(f"  - {sub.get('description', 'Unknown')}: {sub.get('status', 'Unknown')}")
                print(f"    Type: {sub.get('type', 'N/A')}")
                print(f"    Expires: {sub.get('expiration-date', 'N/A')}")
            return subs
        else:
            print(f"  ❌ {response.status_code}: {response.text[:100]}")

    print("\n⚠️  Could not find market data subscription endpoint")
    return None


def test_api_quote_tokens(token):
    """Try to get API quote tokens (DXLink access)."""
    print("\n" + "=" * 60)
    print("API QUOTE TOKENS TEST (Primary DXLink endpoint)")
    print("=" * 60)

    response = requests.get(
        f"{TT_BASE}/api-quote-tokens", headers={"Authorization": f"Bearer {token}"}
    )

    if response.ok:
        print("✅ SUCCESS! DXLink token retrieved:")
        data = response.json()

        # Debug: print raw response
        print("\nRaw response:")
        import json

        print(json.dumps(data, indent=2))

        # Try different possible field names
        token_str = data.get("token") or data.get("data", {}).get("token", "N/A")
        dxlink_url = data.get("dxlink-url") or data.get("data", {}).get("dxlink-url", "N/A")
        websocket_url = data.get("websocket-url") or data.get("data", {}).get(
            "websocket-url", "N/A"
        )
        level = data.get("level") or data.get("data", {}).get("level", "N/A")

        if token_str and token_str != "N/A":
            print(
                f"\n✓ Token: {token_str[:30]}..."
                if len(token_str) > 30
                else f"\n✓ Token: {token_str}"
            )
        if dxlink_url and dxlink_url != "N/A":
            print(f"✓ DXLink URL: {dxlink_url}")
        if websocket_url and websocket_url != "N/A":
            print(f"✓ WebSocket URL: {websocket_url}")
        if level and level != "N/A":
            print(f"✓ Level: {level}")

        print("\n🎉 YOU HAVE DXLINK ACCESS! 🎉")
        return data
    else:
        print(f"❌ FAILED: {response.status_code}")
        print(f"Response: {response.text}")
        return None


def test_quote_streamer_tokens(token):
    """Alternative endpoint for streaming tokens."""
    print("\n" + "=" * 60)
    print("QUOTE STREAMER TOKENS TEST (Alternative endpoint)")
    print("=" * 60)

    response = requests.get(
        f"{TT_BASE}/quote-streamer-tokens", headers={"Authorization": f"Bearer {token}"}
    )

    if response.ok:
        print("✅ SUCCESS! Streamer token retrieved:")
        data = response.json()
        print(data)
        return data
    else:
        print(f"❌ FAILED: {response.status_code}")
        print(f"Response: {response.text}")
        return None


def test_dxlink_websocket_url(token):
    """Try to get DXLink WebSocket URL."""
    print("\n" + "=" * 60)
    print("DXLINK WEBSOCKET URL TEST")
    print("=" * 60)

    response = requests.get(
        f"{TT_BASE}/dxlink-tokens", headers={"Authorization": f"Bearer {token}"}
    )

    if response.ok:
        print("✅ SUCCESS! DXLink websocket info retrieved:")
        data = response.json()
        print(data)
        return data
    else:
        print(f"❌ FAILED: {response.status_code}")
        print(f"Response: {response.text}")
        return None


def print_diagnosis(results):
    """Print final diagnosis and recommendations."""
    print("\n" + "=" * 60)
    print("DIAGNOSIS & RECOMMENDATIONS")
    print("=" * 60)

    has_access = results.get("api_quote_tokens") is not None

    if has_access:
        print("\n✅ ✅ ✅  YOU HAVE DXLINK ACCESS!  ✅ ✅ ✅\n")
        print("Next steps:")
        print("1. Implement DXLink WebSocket client")
        print("2. Subscribe to real-time quotes for futures/equities")
        print("3. Subscribe to Greeks feed")
        print("4. Replace legacy provider with DXLink streaming\n")
        print("Recommended implementation:")
        print("  - Use tastytrade Python SDK (pip install tastytrade)")
        print("  - Or use dxfeed-graal-python-api directly")
        print("  - Estimated effort: 8-12 hours")
        print("\nBenefit: 100% data reliability, zero additional providers needed")

    else:
        print("\n❌ DXLink access NOT available\n")
        print("Possible reasons:")
        print("1. Account lacks streaming entitlement")
        print("   → Contact Tastytrade support: support@tastytrade.com")
        print("   → Ask: 'How do I enable DXLink/DXFeed streaming for my account?'")
        print("")
        print("2. Minimum balance requirement")
        print("   → Some brokers require $2k-5k funded for real-time data")
        print("   → Check account balance and funding requirements")
        print("")
        print("3. Market data agreements not signed")
        print("   → Log into tastytrade.com")
        print("   → Navigate to: Account → Agreements")
        print("   → Sign any pending market data agreements")
        print("")
        print("4. Separate subscription required")
        print("   → Ask support about pricing for streaming access")
        print("   → Compare vs IBKR alternative (~$15/mo)")
        print("\nAlternative solution:")
        print("  - Integrate IBKR API for futures data ($15/mo)")
        print("  - Keep Tastytrade for IV/HV metrics (free)")
        print("  - Estimated effort: 8-10 hours")


def main():
    """Run all diagnostic tests."""
    print("=" * 60)
    print("TASTYTRADE DXLINK ACCESS DIAGNOSTIC")
    print("=" * 60)
    print("\nThis script will test whether your Tastytrade account")
    print("has access to DXLink/DXFeed streaming (real-time quotes + Greeks)\n")

    # Results tracking
    results = {}

    # Step 1: Get OAuth access token
    token = get_oauth_access_token()
    if not token:
        print("\n❌ Cannot proceed - OAuth authentication failed")
        print("\nCheck that .env.tastytrade contains:")
        print("  export TT_CLIENT_ID=...")
        print("  export TT_CLIENT_SECRET=...")
        print("  export TT_REFRESH_TOKEN=...")
        return

    # Step 2: Check customer info and entitlements
    customer = check_customer_entitlements(token)
    results["customer"] = customer

    # Step 3: Check market data subscriptions
    if customer and customer.get("accounts"):
        account_number = customer["accounts"][0]["account-number"]
        subs = check_market_data_subscriptions(token, account_number)
        results["subscriptions"] = subs

    # Step 4: Test DXLink endpoints
    api_tokens = test_api_quote_tokens(token)
    results["api_quote_tokens"] = api_tokens

    if not api_tokens:
        # Try alternative endpoints
        streamer_tokens = test_quote_streamer_tokens(token)
        results["quote_streamer_tokens"] = streamer_tokens

        dxlink_url = test_dxlink_websocket_url(token)
        results["dxlink_websocket"] = dxlink_url

    # Step 5: Print diagnosis
    print_diagnosis(results)

    print("\n" + "=" * 60)
    print("For questions or issues, contact Tastytrade:")
    print("  Email: support@tastytrade.com")
    print("  Phone: 1-312-675-7257")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
