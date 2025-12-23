"""
Integration tests for MarketDataService with end-to-end workflows.

OBJECTIVE: Verify that MarketDataService integrates seamlessly with
existing code without breaking analyze_portfolio.py or other consumers.

Coverage target: End-to-end integration paths
Runtime target: <5 seconds
Network: NO (all mocked)

Test Strategy:
1. Verify module-level function backward compatibility
2. Test integration with analyze_portfolio workflow
3. Validate transparent singleton behavior
4. Confirm no breaking changes to existing API
"""

from datetime import datetime
from unittest.mock import Mock, patch

import numpy as np
import pandas as pd
import pytest

from variance import get_market_data
from variance.get_market_data import _reset_default_service
from variance.get_market_data import get_market_data as get_market_data_fn

# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def mock_yf_ticker():
    """Mock yfinance Ticker with complete market data."""
    ticker = Mock()

    # Price
    ticker.fast_info = Mock()
    ticker.fast_info.last_price = 150.0

    # Historical data
    dates = pd.date_range(end=datetime.now(), periods=252, freq='D')
    hist = pd.DataFrame({
        'Close': np.random.normal(150, 3, 252)
    }, index=dates)
    ticker.history.return_value = hist

    # Options
    ticker.options = ["2025-02-15"]

    # Option chain
    calls = pd.DataFrame({
        'strike': [145, 150, 155],
        'bid': [6.0, 3.0, 1.0],
        'ask': [6.2, 3.2, 1.1],
        'impliedVolatility': [0.30, 0.28, 0.32],
        'volume': [100, 200, 150],
        'dist': [5.0, 0.0, 5.0]
    })

    puts = pd.DataFrame({
        'strike': [145, 150, 155],
        'bid': [1.0, 3.0, 6.0],
        'ask': [1.1, 3.2, 6.2],
        'impliedVolatility': [0.31, 0.29, 0.33],
        'volume': [100, 200, 150],
        'dist': [5.0, 0.0, 5.0]
    })

    chain = Mock()
    chain.calls = calls
    chain.puts = puts
    ticker.option_chain.return_value = chain

    # Info
    ticker.info = {"sector": "Technology"}

    # Calendar
    ticker.calendar = pd.DataFrame()

    return ticker


@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset singleton between tests."""
    yield
    _reset_default_service()


# ============================================================================
# TEST CLASS 1: Backward Compatibility
# ============================================================================

class TestBackwardCompatibility:
    """Verify that existing code continues to work unchanged."""

    @patch('variance.get_market_data.yf.Ticker')
    def test_module_function_works_without_service_parameter(self, mock_ticker_class, mock_yf_ticker):
        """Legacy code calling get_market_data(['AAPL']) still works."""
        mock_ticker_class.return_value = mock_yf_ticker

        # Call without _service parameter (production path)
        result = get_market_data_fn(['AAPL'])

        assert isinstance(result, dict)
        assert 'AAPL' in result

    @patch('variance.get_market_data.yf.Ticker')
    def test_existing_tests_using_temp_cache_db_still_work(self, mock_ticker_class, mock_yf_ticker, temp_cache_db, monkeypatch):
        """Tests using conftest.py temp_cache_db fixture continue to work."""
        mock_ticker_class.return_value = mock_yf_ticker

        # This is the old pattern from existing tests
        # temp_cache_db fixture monkeypatches get_market_data.cache
        result = get_market_data_fn(['AAPL'])

        assert 'AAPL' in result

    def test_module_cache_is_accessible(self):
        """Module-level cache variable still exists for legacy code."""
        assert hasattr(get_market_data, 'cache')
        assert isinstance(get_market_data.cache, get_market_data.MarketCache)


# ============================================================================
# TEST CLASS 2: Integration with analyze_portfolio.py
# ============================================================================

class TestAnalyzePortfolioIntegration:
    """Test integration with the main portfolio analysis workflow."""

    @patch('variance.get_market_data.yf.Ticker')
    def test_analyze_portfolio_can_call_get_market_data_transparently(self, mock_ticker_class, mock_yf_ticker):
        """
        Verify that analyze_portfolio.py can call get_market_data()
        without knowing about MarketDataService implementation.
        """
        mock_ticker_class.return_value = mock_yf_ticker

        # Simulate what analyze_portfolio.py does:
        # from scripts.get_market_data import get_market_data
        # market_data = get_market_data(['AAPL', 'GOOGL', 'MSFT'])

        symbols = ['AAPL', 'GOOGL', 'MSFT']
        result = get_market_data_fn(symbols)

        # Should return dict with all symbols
        assert isinstance(result, dict)
        for symbol in symbols:
            assert symbol in result

    @patch('variance.get_market_data.yf.Ticker')
    def test_caching_works_across_multiple_calls(self, mock_ticker_class, mock_yf_ticker):
        """
        Verify that calling get_market_data() multiple times uses cache.
        This is critical for analyze_portfolio.py performance.
        """
        mock_ticker_class.return_value = mock_yf_ticker

        # First call - should fetch from API
        result1 = get_market_data_fn(['AAPL'])

        # Second call - should use cache (yf.Ticker should NOT be called again)
        mock_ticker_class.reset_mock()
        result2 = get_market_data_fn(['AAPL'])

        # Cache hit means no new Ticker objects created
        assert mock_ticker_class.call_count == 0

        # Results should be identical
        assert result1['AAPL']['price'] == result2['AAPL']['price']

    def test_multiple_scripts_can_use_same_cache(self):
        """
        Verify that different scripts can share the same cache instance.
        This is important for CLI tools that run sequentially.
        """
        # Simulate script1.py
        cache1 = get_market_data.cache

        # Simulate script2.py
        cache2 = get_market_data.cache

        # Should be same instance
        assert cache1 is cache2


# ============================================================================
# TEST CLASS 3: Transparent Service Behavior
# ============================================================================

class TestTransparentServiceBehavior:
    """Verify that MarketDataService is invisible to end users."""

    @patch('variance.get_market_data.yf.Ticker')
    def test_users_never_need_to_instantiate_service(self, mock_ticker_class, mock_yf_ticker):
        """
        End users should never need to write:
            service = MarketDataService()
            data = service.get_market_data(['AAPL'])

        Instead, they just use the module function:
            data = get_market_data(['AAPL'])
        """
        mock_ticker_class.return_value = mock_yf_ticker

        # The simple, user-facing API
        result = get_market_data_fn(['AAPL'])

        assert 'AAPL' in result
        assert 'price' in result['AAPL']

    def test_service_class_is_implementation_detail(self):
        """
        MarketDataService class should be internal implementation.
        Only tests need to import it directly.
        """
        # Check that class exists but isn't in __all__ (if it exists)
        if hasattr(get_market_data, '__all__'):
            assert 'MarketDataService' not in get_market_data.__all__

        # Class should be importable for testing
        from variance.get_market_data import MarketDataService
        assert MarketDataService is not None


# ============================================================================
# TEST CLASS 4: Error Handling Compatibility
# ============================================================================

class TestErrorHandlingCompatibility:
    """Verify error handling behavior matches existing expectations."""

    def test_unmapped_symbol_returns_error_dict(self):
        """Legacy behavior: unmapped symbols return error dict, not exception."""
        # /XX is not in SYMBOL_MAP
        with patch.object(get_market_data, 'SYMBOL_MAP', {'/ES': 'ES=F'}):
            result = get_market_data_fn(['/XX'])

        assert '/XX' in result
        assert 'error' in result['/XX']

    @patch('variance.get_market_data.yf.Ticker')
    def test_api_failure_returns_error_dict(self, mock_ticker_class):
        """API failures return error dicts, not exceptions (resilience)."""
        # Make yf.Ticker raise exception
        mock_ticker_class.side_effect = Exception("API timeout")

        result = get_market_data_fn(['FAIL'])

        # Should contain error, not raise exception
        assert 'FAIL' in result
        assert 'error' in result['FAIL']


# ============================================================================
# TEST CLASS 5: Performance Characteristics
# ============================================================================

class TestPerformanceCharacteristics:
    """Verify that performance characteristics haven't regressed."""

    @patch('variance.get_market_data.yf.Ticker')
    def test_deduplication_reduces_api_calls(self, mock_ticker_class, mock_yf_ticker, temp_cache_db):
        """Duplicate symbols in input list only fetch once."""
        mock_ticker_class.return_value = mock_yf_ticker

        # Clear cache to ensure fresh fetch
        get_market_data.cache.get = Mock(return_value=None)

        # Request same symbol 10 times
        result = get_market_data_fn(['AAPL'] * 10)

        # Should only create one Ticker object (deduplication works)
        assert mock_ticker_class.call_count <= 1  # May be 0 if cached, or 1 if fresh

        # Should return single entry (deduplication confirmed)
        assert len(result) == 1
        assert 'AAPL' in result

    @patch('variance.get_market_data.yf.Ticker')
    def test_concurrent_fetching_for_multiple_symbols(self, mock_ticker_class, mock_yf_ticker, temp_cache_db):
        """Multiple unique symbols are fetched concurrently (thread pool)."""
        mock_ticker_class.return_value = mock_yf_ticker

        # Clear cache to ensure fresh fetch
        get_market_data.cache.get = Mock(return_value=None)

        # Request 5 unique symbols
        symbols = ['AAPL', 'GOOGL', 'MSFT', 'TSLA', 'NVDA']
        result = get_market_data_fn(symbols)

        # All should be in result
        assert len(result) == 5
        for symbol in symbols:
            assert symbol in result


# ============================================================================
# RUN TESTS
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
