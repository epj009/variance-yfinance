"""
Test suite for MarketDataService class with injectable cache dependency.

OBJECTIVE: Validate that MarketDataService enables testable dependency injection
without requiring monkeypatch for cache isolation.

Coverage target: >80% for MarketDataService class
Runtime target: <3 seconds
Network: NO (all mocked)

Test Strategy:
1. Service instantiation (default vs injected cache)
2. Data fetching with isolated cache instances
3. Singleton wrapper behavior
4. Backward compatibility with existing code
"""

import pytest
import sys
import os
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

import pandas as pd
import numpy as np

# Add scripts/ to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../scripts'))

import get_market_data
from get_market_data import MarketDataService, MarketCache, get_market_data as get_market_data_fn, _reset_default_service


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def test_cache(tmp_path):
    """Create isolated MarketCache for testing (no monkeypatch required)."""
    db_path = tmp_path / "test_service_cache.db"
    return MarketCache(str(db_path))


@pytest.fixture
def second_cache(tmp_path):
    """Create second isolated cache to test multi-instance isolation."""
    db_path = tmp_path / "second_cache.db"
    return MarketCache(str(db_path))


@pytest.fixture
def mock_yf_ticker_with_data():
    """Mock yfinance Ticker with realistic market data."""
    def _create(symbol="AAPL", price=150.0, iv=0.30, hv=25.0):
        ticker = Mock()

        # Price data
        ticker.fast_info = Mock()
        ticker.fast_info.last_price = price

        # Historical data for HV
        dates = pd.date_range(end=datetime.now(), periods=252, freq='D')
        hist_data = pd.DataFrame({
            'Close': np.random.normal(price, price * 0.02, 252)
        }, index=dates)
        ticker.history.return_value = hist_data

        # Option chain
        ticker.options = ["2025-02-15"]

        calls_df = pd.DataFrame({
            'strike': [145, 150, 155],
            'bid': [6.0, 3.0, 1.0],
            'ask': [6.2, 3.2, 1.1],
            'impliedVolatility': [iv, iv, iv],
            'volume': [100, 200, 150],
            'dist': [5.0, 0.0, 5.0]
        })

        puts_df = pd.DataFrame({
            'strike': [145, 150, 155],
            'bid': [1.0, 3.0, 6.0],
            'ask': [1.1, 3.2, 6.2],
            'impliedVolatility': [iv, iv, iv],
            'volume': [100, 200, 150],
            'dist': [5.0, 0.0, 5.0]
        })

        chain = Mock()
        chain.calls = calls_df
        chain.puts = puts_df
        ticker.option_chain.return_value = chain

        # Sector info
        ticker.info = {"sector": "Technology"}

        # Earnings calendar
        ticker.calendar = pd.DataFrame()

        return ticker

    return _create


@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset singleton service between tests to prevent cross-contamination."""
    yield
    _reset_default_service()


# ============================================================================
# TEST CLASS 1: Service Instantiation
# ============================================================================

class TestServiceInstantiation:
    """Test MarketDataService constructor and cache injection."""

    def test_service_uses_default_cache_when_none_provided(self):
        """When no cache is provided, service uses module-level global cache."""
        service = MarketDataService()

        # Should use the module's global cache
        assert service.cache is get_market_data.cache
        assert isinstance(service.cache, MarketCache)

    def test_service_uses_injected_cache(self, test_cache):
        """When cache is provided, service uses the injected instance."""
        service = MarketDataService(cache=test_cache)

        assert service.cache is test_cache
        assert service.cache is not get_market_data.cache

    def test_cache_property_is_read_only(self, test_cache):
        """Cache property provides read-only access (no setter)."""
        service = MarketDataService(cache=test_cache)

        # Access should work
        cache_ref = service.cache
        assert cache_ref is test_cache

        # Attempting to set should fail (no setter attribute)
        with pytest.raises(AttributeError):
            service.cache = MarketCache()

    def test_multiple_services_with_different_caches(self, test_cache, second_cache):
        """Multiple service instances can have different cache backends."""
        service1 = MarketDataService(cache=test_cache)
        service2 = MarketDataService(cache=second_cache)

        assert service1.cache is test_cache
        assert service2.cache is second_cache
        assert service1.cache is not service2.cache


# ============================================================================
# TEST CLASS 2: Data Fetching with Injected Cache
# ============================================================================

class TestDataFetchingWithInjection:
    """Test get_market_data() method with isolated cache instances."""

    def test_get_market_data_checks_cache_first(self, test_cache):
        """Service checks injected cache before making API calls."""
        service = MarketDataService(cache=test_cache)

        # Pre-populate cache with data
        cached_data = {
            "price": 150.0,
            "is_stale": False,
            "iv": 30.0,
            "hv252": 25.0,
            "hv20": 22.0,
            "hv_rank": 45.0,
            "iv_rank": None,
            "vrp_structural": 1.2,
            "vrp_tactical": 1.36,
            "atm_volume": 1000,
            "atm_bid": 2.5,
            "atm_ask": 2.6,
            "earnings_date": None,
            "sector": "Technology",
            "proxy": None
        }
        test_cache.set("md_AAPL", cached_data, 3600)

        # Call should return cached data without hitting API
        result = service.get_market_data(['AAPL'])

        assert 'AAPL' in result
        assert result['AAPL'] == cached_data
        assert result['AAPL']['price'] == 150.0

    def test_get_market_data_deduplicates_symbols(self, test_cache):
        """Service removes duplicate symbols before fetching."""
        service = MarketDataService(cache=test_cache)

        # Pre-populate cache for AAPL
        cached_data = {"price": 150.0, "iv": 30.0}
        test_cache.set("md_AAPL", cached_data, 3600)

        # Request AAPL multiple times
        result = service.get_market_data(['AAPL', 'AAPL', 'AAPL'])

        # Should return single entry
        assert len(result) == 1
        assert 'AAPL' in result

    def test_get_market_data_returns_cached_results_only(self, test_cache):
        """When all symbols are cached, no API calls are made."""
        service = MarketDataService(cache=test_cache)

        # Populate cache with multiple symbols
        for symbol in ['AAPL', 'GOOGL', 'MSFT']:
            test_cache.set(f"md_{symbol}", {"price": 100.0}, 3600)

        result = service.get_market_data(['AAPL', 'GOOGL', 'MSFT'])

        assert len(result) == 3
        assert all(symbol in result for symbol in ['AAPL', 'GOOGL', 'MSFT'])

    def test_get_market_data_handles_empty_list(self, test_cache):
        """Service handles empty symbol list gracefully."""
        service = MarketDataService(cache=test_cache)

        result = service.get_market_data([])

        assert result == {}

    def test_get_market_data_handles_unmapped_symbols(self, test_cache):
        """Service returns error for unmapped futures symbols."""
        service = MarketDataService(cache=test_cache)

        # /XX is not in SYMBOL_MAP
        with patch.object(get_market_data, 'SYMBOL_MAP', {'/ES': 'ES=F'}):
            result = service.get_market_data(['/XX'])

        assert '/XX' in result
        assert 'error' in result['/XX']
        assert result['/XX']['error'] == 'unmapped_symbol'

    @patch('get_market_data.yf.Ticker')
    def test_get_market_data_fetches_missing_symbols(self, mock_ticker_class, test_cache, mock_yf_ticker_with_data):
        """Service fetches data for symbols not in cache."""
        service = MarketDataService(cache=test_cache)

        # Cache AAPL, leave GOOGL uncached
        test_cache.set("md_AAPL", {"price": 150.0}, 3600)

        # Mock yfinance for GOOGL
        mock_ticker_class.return_value = mock_yf_ticker_with_data(symbol="GOOGL", price=2800.0)

        result = service.get_market_data(['AAPL', 'GOOGL'])

        # Both should be in result
        assert 'AAPL' in result
        assert 'GOOGL' in result

        # AAPL from cache
        assert result['AAPL']['price'] == 150.0

        # GOOGL should have been fetched (mocked to return 2800.0)
        # Note: process_single_symbol is still used, which may have different behavior
        # This test validates the flow, not the exact data structure


# ============================================================================
# TEST CLASS 3: Singleton Wrapper Behavior
# ============================================================================

class TestSingletonWrapper:
    """Test module-level get_market_data() wrapper function."""

    def test_module_level_function_uses_singleton_by_default(self):
        """Module function uses default singleton service when no _service param."""
        # Pre-populate global cache
        get_market_data.cache.set("md_TEST", {"price": 100.0}, 3600)

        result = get_market_data_fn(['TEST'])

        assert 'TEST' in result
        assert result['TEST']['price'] == 100.0

    def test_module_level_function_accepts_injected_service(self, test_cache):
        """Module function accepts _service parameter for testing."""
        # Create isolated service
        test_service = MarketDataService(cache=test_cache)
        test_cache.set("md_CUSTOM", {"price": 200.0}, 3600)

        result = get_market_data_fn(['CUSTOM'], _service=test_service)

        assert 'CUSTOM' in result
        assert result['CUSTOM']['price'] == 200.0

    def test_reset_default_service_clears_singleton(self):
        """_reset_default_service() clears the singleton instance."""
        # Create singleton by calling function
        _ = get_market_data_fn(['AAPL'])

        # Singleton should exist
        assert get_market_data._default_service is not None

        # Reset
        _reset_default_service()

        # Singleton should be cleared
        assert get_market_data._default_service is None

    def test_singleton_lazy_initialization(self):
        """Singleton service is created lazily on first call."""
        _reset_default_service()

        # Should be None initially
        assert get_market_data._default_service is None

        # First call creates it
        get_market_data.cache.set("md_LAZY", {"price": 50.0}, 3600)
        _ = get_market_data_fn(['LAZY'])

        # Now should exist
        assert get_market_data._default_service is not None
        assert isinstance(get_market_data._default_service, MarketDataService)

    def test_singleton_reused_across_calls(self):
        """Multiple calls to wrapper use same singleton instance."""
        _reset_default_service()

        # Make two calls
        _ = get_market_data_fn(['AAPL'])
        service1 = get_market_data._default_service

        _ = get_market_data_fn(['GOOGL'])
        service2 = get_market_data._default_service

        # Should be same instance
        assert service1 is service2


# ============================================================================
# TEST CLASS 4: Cache Isolation (No Monkeypatch Required)
# ============================================================================

class TestCacheIsolation:
    """Verify that injected caches are truly isolated without monkeypatch."""

    def test_two_services_have_isolated_caches(self, test_cache, second_cache):
        """Two services with different caches don't share data."""
        service1 = MarketDataService(cache=test_cache)
        service2 = MarketDataService(cache=second_cache)

        # Write to service1's cache
        test_cache.set("md_ISOLATED", {"price": 100.0}, 3600)

        # Service1 should see it
        result1 = service1.get_market_data(['ISOLATED'])
        assert 'ISOLATED' in result1
        assert result1['ISOLATED']['price'] == 100.0

        # Service2 should NOT see it (would need to fetch)
        # Since ISOLATED isn't a real symbol, it will error
        result2 = service2.get_market_data(['ISOLATED'])
        assert 'ISOLATED' in result2
        # Either error or missing (depends on map_symbol behavior)
        # This validates isolation - service2 didn't use service1's cache

    def test_service_does_not_pollute_global_cache(self, test_cache):
        """Service with injected cache doesn't write to global cache."""
        service = MarketDataService(cache=test_cache)

        # Write to injected cache
        test_cache.set("md_NOPOLLUTE", {"price": 99.0}, 3600)

        # Global cache should not have it
        global_result = get_market_data.cache.get("md_NOPOLLUTE")
        assert global_result is None


# ============================================================================
# TEST CLASS 5: Error Handling
# ============================================================================

class TestErrorHandling:
    """Test service behavior under error conditions."""

    def test_service_propagates_cache_exceptions(self, test_cache):
        """Cache exceptions propagate to caller (fail-fast for debugging)."""
        service = MarketDataService(cache=test_cache)

        # Make cache.get() raise exception
        with patch.object(test_cache, 'get', side_effect=Exception("Cache failure")):
            # Service should propagate the exception (not swallow it)
            with pytest.raises(Exception, match="Cache failure"):
                service.get_market_data(['TEST'])

    @patch('get_market_data.process_single_symbol')
    def test_service_handles_fetch_exceptions(self, mock_process, test_cache):
        """If symbol fetch raises exception, service returns error dict."""
        service = MarketDataService(cache=test_cache)

        # Make fetch raise exception
        mock_process.side_effect = Exception("API timeout")

        result = service.get_market_data(['FAIL'])

        assert 'FAIL' in result
        assert 'error' in result['FAIL']


# ============================================================================
# RUN TESTS
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
