"""
Comprehensive test suite for scripts/get_market_data.py
Updated for decoupled architecture and robust math.
"""

from unittest.mock import Mock, patch

import pandas as pd
import pytest

from variance import get_market_data
from variance.get_market_data import (
    MarketCache,
    get_current_iv,
    normalize_iv,
)

# ============================================================================
# TEST CLASS 1: normalize_iv() - CRITICAL PRIORITY
# ============================================================================


class TestNormalizeIV:
    """
    Unit tests for IV normalization - CRITICAL for trading accuracy.
    """

    def test_normalize_iv_clear_percentage(self):
        """IV > 1.5 is always treated as percentage format."""
        iv, warning = normalize_iv(32.5, hv_context=None)
        assert iv == 32.5
        assert warning is None

    def test_normalize_iv_decimal_to_percent_no_context(self):
        """Decimal IV (0.325) converted to percentage (32.5%) without context."""
        iv, warning = normalize_iv(0.325, hv_context=None)
        assert iv == 32.5
        assert warning == "iv_scale_assumed_decimal"

    def test_normalize_iv_uses_distance_to_context(self):
        """
        Case: IV=0.25, HV=20.0.
        Scaled: 25.0 (dist 5.0)
        Unscaled: 0.25 (dist 19.75)
        Should scale.
        """
        iv, warning = normalize_iv(0.25, hv_context=20.0)
        assert iv == 25.0
        assert warning == "iv_scale_corrected"

    def test_normalize_iv_handles_ambiguous_correctly(self):
        """
        Case: IV=0.5, HV=5.0.
        Scaled: 50.0 (dist 45.0)
        Unscaled: 0.5 (dist 4.5)
        Clinical Result: 0.5 is closer to context. No scaling.
        """
        iv, warning = normalize_iv(0.5, hv_context=5.0)
        assert iv == 0.5
        assert warning is None

    def test_normalize_iv_corrects_high_decimal(self):
        """Boundary: IV=1.0 treated as decimal (100%) when context is 15%."""
        iv, warning = normalize_iv(1.0, hv_context=15.0)
        assert iv == 100.0
        assert warning == "iv_scale_corrected"

    def test_normalize_iv_handles_low_vol_context(self):
        """
        Case: IV=1.5, HV=5.0.
        Log-Dist Unscaled: |log(1.5/5.0)| = 1.2
        Log-Dist Scaled:   |log(150/5.0)| = 3.4
        Result: 1.5 is closer. No scaling.
        """
        iv, warning = normalize_iv(1.5, hv_context=5.0)
        assert iv == 1.5
        assert warning is None


# ============================================================================
# TEST CLASS 2: MarketCache - HIGH PRIORITY
# ============================================================================


class TestMarketCache:
    """Test the SQLite caching engine."""

    def test_cache_set_and_get(self, temp_cache_db):
        """Basic set/get functionality."""
        cache = MarketCache(str(temp_cache_db))
        test_data = {"iv": 30.5, "hv": 25.0}
        cache.set("test_key", test_data, ttl_seconds=3600)
        assert cache.get("test_key") == test_data

    def test_cache_miss_returns_none(self, temp_cache_db):
        """Missing key returns None."""
        cache = MarketCache(str(temp_cache_db))
        assert cache.get("nonexistent") is None


# ============================================================================
# TEST CLASS 3: get_current_iv() - HIGH PRIORITY
# ============================================================================


class TestGetCurrentIV:
    """Test option chain IV extraction and gating."""

    def test_get_iv_happy_path(self, temp_cache_db, mock_ticker_factory, mock_option_chain):
        """Standard IV extraction from ATM options."""
        calls, puts = mock_option_chain
        ticker = mock_ticker_factory(
            options=["2025-02-15"], option_chain_calls=calls, option_chain_puts=puts
        )

        # Should return data dict
        result = get_current_iv(ticker, 150.0, "AAPL", hv_context=25.0)
        assert pytest.approx(result["iv"]) == 28.0
        assert result["atm_vol"] > 0

    def test_get_iv_rejects_illiquid(self, temp_cache_db, mock_ticker_factory):
        """Returns empty dict if no liquidity."""
        empty_df = pd.DataFrame({"bid": [0], "ask": [0]})
        ticker = mock_ticker_factory(option_chain_calls=empty_df, option_chain_puts=empty_df)
        result = get_current_iv(ticker, 150.0, "AAPL")
        assert result == {}

    def test_get_iv_uses_cache(self, temp_cache_db):
        """Cached IV is returned without API call."""
        cache = MarketCache(str(temp_cache_db))
        cached_value = {"iv": 28.5, "atm_vol": 1000}
        cache.set("iv_AAPL", cached_value, 3600)

        with patch.object(get_market_data, "cache", cache):
            ticker = Mock()
            ticker.options = []  # Should not be called
            result = get_current_iv(ticker, 150.0, "AAPL")
            assert result == cached_value
