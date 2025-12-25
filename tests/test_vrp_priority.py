"""
Test VRP calculation priority: Tastytrade (HV90/HV30) over yfinance (HV252/HV20).

This test verifies the critical fix where VRP calculations were backwards,
preferring yfinance data over Tastytrade data.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from variance.get_market_data import TastytradeProvider


def test_vrp_structural_prefers_tastytrade():
    """Verify VRP structural uses HV90 (Tastytrade) over HV252 (yfinance)."""
    provider = TastytradeProvider()

    # Simulate AAPL data from the bug report
    # Note: IV goes in merged_data, HV values in tt_data/yf_data
    merged_data = {
        "symbol": "AAPL",
        "iv": 18.56,  # This comes from Tastytrade in production
    }

    tt_data = {
        "symbol": "AAPL",
        "hv90": 17.62,  # Tastytrade - should be used for structural
        "hv30": 15.0,  # Tastytrade - should be used for tactical
    }

    yf_data = {
        "symbol": "AAPL",
        "hv252": 32.17,  # yfinance - should NOT be used for structural VRP
        "hv20": 20.0,  # yfinance - should NOT be used for tactical VRP
    }

    merged = provider._compute_vrp(merged_data, tt_data, yf_data)

    # Expected VRP structural: IV / HV90 = 18.56 / 17.62 = 1.054
    # NOT: IV / HV252 = 18.56 / 32.17 = 0.577 (old bug)
    expected_structural = 18.56 / 17.62
    expected_tactical = 18.56 / 15.0

    assert merged.get("vrp_structural") is not None, "VRP structural should be computed"
    assert merged.get("vrp_tactical") is not None, "VRP tactical should be computed"

    actual_structural = merged["vrp_structural"]
    actual_tactical = merged["vrp_tactical"]

    print(f"✓ VRP Structural: {actual_structural:.3f} (expected ~{expected_structural:.3f})")
    print(f"✓ VRP Tactical: {actual_tactical:.3f} (expected ~{expected_tactical:.3f})")

    # Verify it's using HV90, not HV252
    assert abs(actual_structural - expected_structural) < 0.01, (
        f"Expected {expected_structural:.3f}, got {actual_structural:.3f} - using wrong HV source!"
    )

    assert abs(actual_tactical - expected_tactical) < 0.01, (
        f"Expected {expected_tactical:.3f}, got {actual_tactical:.3f} - using wrong HV source!"
    )

    print("✓ VRP calculations correctly prefer Tastytrade data")


def test_vrp_fallback_to_yfinance():
    """Verify VRP falls back to yfinance when Tastytrade data unavailable."""
    provider = TastytradeProvider()

    # Simulate case where Tastytrade data is missing
    merged_data = {
        "symbol": "TEST",
        "iv": 25.0,
    }

    tt_data = {
        "symbol": "TEST",
        # No HV90 or HV30
    }

    yf_data = {
        "symbol": "TEST",
        "hv252": 20.0,  # Should be used for structural
        "hv20": 18.0,  # Should be used for tactical
    }

    merged = provider._compute_vrp(merged_data, tt_data, yf_data)

    expected_structural = 25.0 / 20.0  # Should use HV252
    expected_tactical = 25.0 / 18.0  # Should use HV20

    actual_structural = merged.get("vrp_structural")
    actual_tactical = merged.get("vrp_tactical")

    assert actual_structural is not None, "Should fallback to HV252"
    assert actual_tactical is not None, "Should fallback to HV20"

    assert abs(actual_structural - expected_structural) < 0.01
    assert abs(actual_tactical - expected_tactical) < 0.01

    print("✓ VRP correctly falls back to yfinance when Tastytrade unavailable")


def test_hv_floor_applied():
    """Verify HV floor prevents division by near-zero values."""
    provider = TastytradeProvider()

    # Simulate low HV scenario (< 5.0%)
    merged_data = {
        "symbol": "LOWVOL",
        "iv": 10.0,
    }

    tt_data = {
        "symbol": "LOWVOL",
        "hv90": 2.0,  # Below default HV_FLOOR_PERCENT (5.0)
        "hv30": 1.5,  # Below floor
    }

    merged = provider._compute_vrp(merged_data, tt_data, None)

    # Expected: IV / max(HV90, 5.0) = 10.0 / 5.0 = 2.0
    # NOT: 10.0 / 2.0 = 5.0 (without floor)
    expected_structural = 10.0 / 5.0
    expected_tactical = 10.0 / 5.0

    actual_structural = merged.get("vrp_structural")
    actual_tactical = merged.get("vrp_tactical")

    assert actual_structural is not None
    assert actual_tactical is not None

    assert abs(actual_structural - expected_structural) < 0.01, (
        f"HV floor not applied! Expected {expected_structural}, got {actual_structural}"
    )

    assert abs(actual_tactical - expected_tactical) < 0.01, (
        f"HV floor not applied to tactical! Expected {expected_tactical}, got {actual_tactical}"
    )

    print("✓ HV floor correctly applied to prevent division by near-zero")


if __name__ == "__main__":
    print("Testing VRP Calculation Priority (Tastytrade-first)...\n")

    try:
        test_vrp_structural_prefers_tastytrade()
        print()
        test_vrp_fallback_to_yfinance()
        print()
        test_hv_floor_applied()
        print("\n" + "=" * 60)
        print("✓ ALL TESTS PASSED")
        print("=" * 60)
    except AssertionError as e:
        print(f"\n✗ TEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
