"""
Comprehensive test suite for scripts/get_market_data.py

Coverage target: 80%+
Runtime target: <5 seconds
Network: NO (all mocked)

Priority:
1. normalize_iv() - CRITICAL (100% coverage required)
2. MarketCache - HIGH (thread safety, TTL)
3. get_current_iv() - HIGH (zero liquidity, normalization)
"""

import pytest
import sys
import os
import time
import threading
from unittest.mock import Mock, patch, PropertyMock
from datetime import datetime, timedelta

import pandas as pd
import numpy as np

# Add scripts/ to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../scripts'))

import get_market_data


# ============================================================================
# TEST CLASS 1: normalize_iv() - CRITICAL PRIORITY
# ============================================================================

class TestNormalizeIV:
    """
    Unit tests for IV normalization - CRITICAL for trading accuracy.

    Bug impact: 0.5% vs 50% confusion causes 100x error in trading decisions.
    """

    def test_normalize_iv_clear_percentage(self):
        """IV > 1.0 is already in percentage format."""
        iv, warning = get_market_data.normalize_iv(32.5, hv_context=None)
        assert iv == 32.5
        assert warning is None

    def test_normalize_iv_decimal_to_percent_no_context(self):
        """Decimal IV (0.325) converted to percentage (32.5%) without HV context."""
        iv, warning = get_market_data.normalize_iv(0.325, hv_context=None)
        assert iv == 32.5
        assert warning is None

    def test_normalize_iv_decimal_with_hv_context(self):
        """
        Standard case: IV=0.25 (decimal) with HV=20%.

        Bias if decimal: 25/20 = 1.25 (normal)
        Bias if percent: 0.25/20 = 0.0125 (absurd)

        Should convert to percentage.
        """
        iv, warning = get_market_data.normalize_iv(0.25, hv_context=20.0)
        assert iv == 25.0
        assert warning is None

    def test_normalize_iv_detects_percentage_format(self):
        """
        Edge case: IV=0.5 with HV=5%.

        Bias if decimal: 50/5 = 10.0 (absurd - IV way too high)
        Bias if percent: 0.5/5 = 0.1 (absurd - IV way too low)

        This is ambiguous, but default decimal wins.
        """
        iv, warning = get_market_data.normalize_iv(0.5, hv_context=5.0)
        assert iv == 50.0  # Treated as decimal
        assert warning is None

    def test_normalize_iv_corrects_percent_format(self):
        """
        Edge case: IV=0.25 with HV=30%.

        Bias if decimal: 25/30 = 0.83 (normal)
        Bias if percent: 0.25/30 = 0.008 (absurd)

        Should keep as decimal and multiply by 100.
        """
        iv, warning = get_market_data.normalize_iv(0.25, hv_context=30.0)
        assert iv == 25.0
        assert warning is None

    def test_normalize_iv_zero_hv_context(self):
        """Zero HV treated as no context (default to decimal)."""
        iv, warning = get_market_data.normalize_iv(0.5, hv_context=0)
        assert iv == 50.0
        assert warning is None

    def test_normalize_iv_edge_case_exactly_one(self):
        """Boundary: IV=1.0 treated as decimal (becomes 100%)."""
        iv, warning = get_market_data.normalize_iv(1.0, hv_context=15.0)
        assert iv == 100.0
        assert warning is None

    def test_normalize_iv_decimal_gt_one_with_context(self):
        """
        IV > 1.0 can still be decimal (e.g., 1.5 = 150%) with HV context.
        Should not be treated as 1.5%.
        """
        iv, warning = get_market_data.normalize_iv(1.5, hv_context=60.0)
        assert iv == 150.0
        assert warning is None

    def test_normalize_iv_extreme_low_values(self):
        """Very low IV (0.01) still converted to percentage."""
        iv, warning = get_market_data.normalize_iv(0.01, hv_context=5.0)
        assert iv == 1.0
        assert warning is None

    def test_normalize_iv_high_value_unchanged(self):
        """High IV values (>1.0) treated as percent when bias indicates."""
        iv, warning = get_market_data.normalize_iv(75.5, hv_context=50.0)
        assert iv == 75.5
        assert warning == "iv_scale_corrected_percent"


# ============================================================================
# TEST CLASS 2: MarketCache - HIGH PRIORITY
# ============================================================================

class TestMarketCache:
    """Test SQLite cache behavior and thread safety."""

    def test_cache_set_and_get(self, temp_cache_db):
        """Basic set/get functionality."""
        cache = get_market_data.MarketCache(str(temp_cache_db))
        test_data = {"iv": 30.5, "hv": 25.0}

        cache.set("test_key", test_data, ttl_seconds=3600)
        result = cache.get("test_key")

        assert result == test_data

    def test_cache_miss_returns_none(self, temp_cache_db):
        """Cache miss returns None."""
        cache = get_market_data.MarketCache(str(temp_cache_db))
        result = cache.get("nonexistent_key")
        assert result is None

    def test_cache_expiry_after_ttl(self, temp_cache_db):
        """Cache entries expire after TTL."""
        cache = get_market_data.MarketCache(str(temp_cache_db))
        cache.set("expiring_key", {"data": "test"}, ttl_seconds=1)

        # Should exist immediately
        assert cache.get("expiring_key") is not None

        # Wait for expiry
        time.sleep(1.5)

        # Should be expired
        assert cache.get("expiring_key") is None

    def test_cache_does_not_store_none(self, temp_cache_db):
        """Cache does not store None values (resilience feature)."""
        cache = get_market_data.MarketCache(str(temp_cache_db))

        cache.set("none_key", None, ttl_seconds=3600)

        # Should not be stored
        assert cache.get("none_key") is None

    def test_cache_rejects_error_values(self, temp_cache_db):
        """Cache does not store error dictionaries (resilience feature)."""
        cache = get_market_data.MarketCache(str(temp_cache_db))

        cache.set("error_key", {"error": "no_price"}, ttl_seconds=3600)

        # Should not be stored
        assert cache.get("error_key") is None

    def test_cache_thread_safety_concurrent_writes(self, temp_cache_db):
        """Multiple threads can write simultaneously without corruption."""
        cache = get_market_data.MarketCache(str(temp_cache_db))
        errors = []

        def write_thread(thread_id):
            try:
                for i in range(50):
                    cache.set(f"thread_{thread_id}_key_{i}", {"value": i}, 3600)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=write_thread, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Thread safety violation: {errors}"

        # Verify all keys were written
        for thread_id in range(10):
            for i in range(50):
                assert cache.get(f"thread_{thread_id}_key_{i}") is not None

    def test_cache_isolation_between_tests(self, temp_cache_db):
        """Cache is isolated per test via fixture."""
        cache1 = get_market_data.MarketCache(str(temp_cache_db))
        cache1.set("isolation_test", {"data": "cache1"}, 3600)

        # Create a second cache with different path
        cache2 = get_market_data.MarketCache(str(temp_cache_db.parent / "cache2.db"))
        result = cache2.get("isolation_test")

        # Should not see cache1's data
        assert result is None


# ============================================================================
# TEST CLASS 3: get_current_iv() - HIGH PRIORITY
# ============================================================================

class TestGetCurrentIV:
    """Test implied volatility fetching with option chain processing."""

    def test_get_iv_happy_path(self, temp_cache_db, mock_ticker_factory, mock_option_chain):
        """Successful IV fetch with valid option chain."""
        calls_df, puts_df = mock_option_chain
        ticker = mock_ticker_factory(
            options=["2025-02-15"],  # ~45 DTE from test date
            option_chain_calls=calls_df,
            option_chain_puts=puts_df
        )

        result = get_market_data.get_current_iv(ticker, 150.0, "AAPL", hv_context=25.0)

        assert result is not None
        assert "iv" in result
        assert result["iv"] > 0
        assert "atm_vol" in result
        assert "atm_bid" in result
        assert "atm_ask" in result

    def test_get_iv_rejects_zero_liquidity_calls(self, temp_cache_db, mock_ticker_factory):
        """IV fetch fails when call options have zero bid/ask (illiquid)."""
        calls_df = pd.DataFrame({
            'strike': [145, 150, 155],
            'bid': [0, 0, 0],
            'ask': [0, 0, 0],
            'impliedVolatility': [0.30, 0.28, 0.32],
            'volume': [0, 0, 0],
            'dist': [5.0, 0.0, 5.0]
        })
        puts_df = pd.DataFrame({
            'strike': [145, 150, 155],
            'bid': [1.0, 3.0, 6.0],
            'ask': [1.1, 3.2, 6.3],
            'impliedVolatility': [0.31, 0.28, 0.32],
            'volume': [100, 200, 150],
            'dist': [5.0, 0.0, 5.0]
        })

        ticker = mock_ticker_factory(
            options=["2025-02-15"],
            option_chain_calls=calls_df,
            option_chain_puts=puts_df
        )

        result = get_market_data.get_current_iv(ticker, 150.0, "AAPL", hv_context=25.0)

        assert result is None

    def test_get_iv_rejects_zero_liquidity_puts(self, temp_cache_db, mock_ticker_factory):
        """IV fetch fails when put options have zero bid/ask (illiquid)."""
        calls_df = pd.DataFrame({
            'strike': [145, 150, 155],
            'bid': [6.0, 3.0, 1.0],
            'ask': [6.2, 3.2, 1.1],
            'impliedVolatility': [0.30, 0.28, 0.32],
            'volume': [100, 200, 150],
            'dist': [5.0, 0.0, 5.0]
        })
        puts_df = pd.DataFrame({
            'strike': [145, 150, 155],
            'bid': [0, 0, 0],
            'ask': [0, 0, 0],
            'impliedVolatility': [0.31, 0.28, 0.32],
            'volume': [0, 0, 0],
            'dist': [5.0, 0.0, 5.0]
        })

        ticker = mock_ticker_factory(
            options=["2025-02-15"],
            option_chain_calls=calls_df,
            option_chain_puts=puts_df
        )

        result = get_market_data.get_current_iv(ticker, 150.0, "AAPL", hv_context=25.0)

        assert result is None

    def test_get_iv_no_options_available(self, temp_cache_db, mock_ticker_factory):
        """IV fetch fails when no option expirations available."""
        ticker = mock_ticker_factory(options=[])

        result = get_market_data.get_current_iv(ticker, 150.0, "AAPL", hv_context=25.0)

        assert result is None

    def test_get_iv_empty_option_chain(self, temp_cache_db, mock_ticker_factory):
        """IV fetch fails when option chain DataFrames are empty."""
        empty_df = pd.DataFrame()
        ticker = mock_ticker_factory(
            options=["2025-02-15"],
            option_chain_calls=empty_df,
            option_chain_puts=empty_df
        )

        result = get_market_data.get_current_iv(ticker, 150.0, "AAPL", hv_context=25.0)

        assert result is None

    def test_get_iv_uses_cache(self, temp_cache_db):
        """Cached IV is returned without API call."""
        cache = get_market_data.MarketCache(str(temp_cache_db))
        cached_value = {"iv": 28.5, "atm_vol": 1000, "atm_bid": 2.5, "atm_ask": 2.6}
        cache.set("iv_AAPL", cached_value, 3600)

        # Replace module cache
        with patch.object(get_market_data, 'cache', cache):
            ticker = Mock()
            ticker.options = []  # Would fail if called

            result = get_market_data.get_current_iv(ticker, 150.0, "AAPL", hv_context=25.0)

        assert result == cached_value


# ============================================================================
# TEST CLASS 4: calculate_hv() - MEDIUM PRIORITY
# ============================================================================

class TestCalculateHV:
    """Test historical volatility calculation."""

    def test_hv_calculation_valid_history(self, temp_cache_db, mock_ticker_factory):
        """HV calculation with sufficient price history."""
        # Create 252 days of price data with known volatility
        dates = pd.date_range(end=datetime.now(), periods=252, freq='D')
        prices = pd.DataFrame({
            'Close': np.random.normal(100, 2, 252)  # ~2% daily vol
        }, index=dates)

        ticker = mock_ticker_factory(history_data=prices)

        result = get_market_data.calculate_hv(ticker, "AAPL")

        assert result is not None
        assert isinstance(result, dict)
        assert 'hv252' in result
        assert 'hv20' in result
        assert isinstance(result['hv252'], float)
        assert result['hv252'] > 0

    def test_hv_insufficient_history(self, temp_cache_db, mock_ticker_factory):
        """HV calculation fails with insufficient history."""
        # Only 100 days of data (need 200+)
        dates = pd.date_range(end=datetime.now(), periods=100, freq='D')
        prices = pd.DataFrame({
            'Close': np.random.normal(100, 2, 100)
        }, index=dates)

        ticker = mock_ticker_factory(history_data=prices)

        result = get_market_data.calculate_hv(ticker, "AAPL")

        assert result is None

    def test_hv_empty_history(self, temp_cache_db, mock_ticker_factory):
        """HV calculation fails with empty history."""
        empty_df = pd.DataFrame()
        ticker = mock_ticker_factory(history_data=empty_df)

        result = get_market_data.calculate_hv(ticker, "AAPL")

        assert result is None

    def test_hv_uses_cache(self, temp_cache_db):
        """Cached HV is returned without calculation."""
        cache = get_market_data.MarketCache(str(temp_cache_db))
        cache.set("hv_AAPL", {'hv252': 25.5, 'hv20': 20.0}, 3600)

        with patch.object(get_market_data, 'cache', cache):
            ticker = Mock()
            ticker.history.return_value = pd.DataFrame()  # Would fail if called

            result = get_market_data.calculate_hv(ticker, "AAPL")

        assert result == {'hv252': 25.5, 'hv20': 20.0}

# ============================================================================
# TEST CLASS 5: Utility Functions
# ============================================================================

class TestUtilityFunctions:
    """Test utility/helper functions."""

    def test_map_symbol_futures(self):
        """Futures symbols mapped to yfinance format."""
        assert get_market_data.map_symbol("/ES") == "ES=F"
        assert get_market_data.map_symbol("/NQ") == "NQ=F"
        assert get_market_data.map_symbol("/CL") == "CL=F"

    def test_map_symbol_index(self):
        """Index symbols mapped correctly."""
        assert get_market_data.map_symbol("SPX") == "^SPX"
        assert get_market_data.map_symbol("VIX") == "^VIX"

    def test_map_symbol_equity_unchanged(self):
        """Equity symbols pass through unchanged."""
        assert get_market_data.map_symbol("AAPL") == "AAPL"
        assert get_market_data.map_symbol("TSLA") == "TSLA"

    def test_should_skip_earnings_futures(self):
        """Futures symbols skip earnings."""
        assert get_market_data.should_skip_earnings("/ES", "ES=F") is True
        assert get_market_data.should_skip_earnings("/CL", "CL=F") is True

    def test_should_skip_earnings_etf(self):
        """ETFs in SKIP_EARNINGS skip earnings."""
        assert get_market_data.should_skip_earnings("SPY", "SPY") is True
        assert get_market_data.should_skip_earnings("QQQ", "QQQ") is True

    def test_should_skip_earnings_stock(self):
        """Regular stocks don't skip earnings."""
        assert get_market_data.should_skip_earnings("AAPL", "AAPL") is False
        assert get_market_data.should_skip_earnings("TSLA", "TSLA") is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
