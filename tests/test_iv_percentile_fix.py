"""
Test IV Percentile filter fix - removes double-scaling bug.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from variance.models.market_specs import IVPercentileSpec


def test_iv_percentile_correct_scaling():
    """Verify IV percentile filter uses normalized 0-100 values (not decimal)."""
    spec = IVPercentileSpec(min_percentile=20.0)

    # Test case 1: Below threshold (should fail)
    metrics_low = {"iv_percentile": 15.5}  # 15.5th percentile
    assert not spec.is_satisfied_by(metrics_low), "Should reject 15.5 < 20.0"

    # Test case 2: Above threshold (should pass)
    metrics_high = {"iv_percentile": 77.33}  # 77.33rd percentile (like NFLX)
    assert spec.is_satisfied_by(metrics_high), "Should accept 77.33 > 20.0"

    # Test case 3: Exactly at threshold (should pass)
    metrics_exact = {"iv_percentile": 20.0}
    assert spec.is_satisfied_by(metrics_exact), "Should accept 20.0 >= 20.0"

    # Test case 4: Just below threshold (should fail)
    metrics_just_below = {"iv_percentile": 19.9}
    assert not spec.is_satisfied_by(metrics_just_below), "Should reject 19.9 < 20.0"

    print("✓ IV percentile filter correctly uses 0-100 range (no double-scaling)")


def test_iv_percentile_high_threshold():
    """Test with high threshold (80th percentile = top 20%)."""
    spec = IVPercentileSpec(min_percentile=80.0)

    # Test case 1: Below threshold (should fail)
    metrics_mid = {"iv_percentile": 77.33}  # 77th percentile
    assert not spec.is_satisfied_by(metrics_mid), "Should reject 77.33 < 80.0"

    # Test case 2: Above threshold (should pass)
    metrics_high = {"iv_percentile": 85.0}  # 85th percentile
    assert spec.is_satisfied_by(metrics_high), "Should accept 85.0 > 80.0"

    print("✓ High threshold (80th percentile) works correctly")


def test_iv_percentile_edge_cases():
    """Test edge cases and error handling."""
    spec = IVPercentileSpec(min_percentile=50.0)

    # Missing IV percentile
    metrics_none = {}
    assert not spec.is_satisfied_by(metrics_none), "Should reject missing IV percentile"

    # Explicit None
    metrics_null = {"iv_percentile": None}
    assert not spec.is_satisfied_by(metrics_null), "Should reject None IV percentile"

    # Zero threshold (should pass everything)
    spec_zero = IVPercentileSpec(min_percentile=0.0)
    assert spec_zero.is_satisfied_by({"iv_percentile": 1.0}), "Zero threshold passes all"
    assert spec_zero.is_satisfied_by({}), "Zero threshold passes missing data"

    # Negative threshold (should pass everything)
    spec_neg = IVPercentileSpec(min_percentile=-1.0)
    assert spec_neg.is_satisfied_by({"iv_percentile": 1.0}), "Negative threshold passes all"

    print("✓ Edge cases handled correctly")


def test_regression_no_double_scaling():
    """
    Regression test: Ensure we don't have the old double-scaling bug.

    OLD BUG:
      - Input: 77.33 (already normalized)
      - Code: 77.33 * 100 = 7733
      - Result: 7733 > 20 → ALWAYS PASSES (wrong!)

    FIXED:
      - Input: 77.33
      - Code: 77.33 (no multiplication)
      - Result: 77.33 > 20 → PASSES (correct!)
      - Result: 77.33 > 80 → FAILS (correct!)
    """
    spec_low = IVPercentileSpec(min_percentile=20.0)
    spec_high = IVPercentileSpec(min_percentile=80.0)

    metrics = {"iv_percentile": 77.33}  # NFLX actual value

    # With low threshold (20): Should pass
    assert spec_low.is_satisfied_by(metrics), "77.33 > 20 should pass"

    # With high threshold (80): Should FAIL (this is the regression test)
    assert not spec_high.is_satisfied_by(metrics), (
        "77.33 < 80 should FAIL (old bug would pass due to 7733 > 80)"
    )

    print("✓ Regression test: Double-scaling bug is FIXED")
    print("  - 77.33 > 20 = PASS ✓")
    print("  - 77.33 < 80 = FAIL ✓ (old bug would incorrectly pass)")


if __name__ == "__main__":
    print("Testing IV Percentile Filter Fix...\n")

    try:
        test_iv_percentile_correct_scaling()
        print()
        test_iv_percentile_high_threshold()
        print()
        test_iv_percentile_edge_cases()
        print()
        test_regression_no_double_scaling()
        print("\n" + "=" * 60)
        print("✓ ALL TESTS PASSED")
        print("=" * 60)
        print("\nIV Percentile filter is now working correctly!")
        print("Symbols with IV below threshold will be properly rejected.")
    except AssertionError as e:
        print(f"\n✗ TEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
