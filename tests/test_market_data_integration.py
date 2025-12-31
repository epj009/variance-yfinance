"""
Integration tests for MarketDataService with end-to-end workflows.

OBJECTIVE: Verify that MarketDataService integrates cleanly with
provider architecture and keeps existing behavior intact.
"""

from datetime import datetime
from unittest.mock import Mock, patch

import numpy as np
import pandas as pd
import pytest

from variance.market_data import service as service_module
from variance.market_data import settings as md_settings
from variance.market_data.service import _reset_default_service, get_market_data


@pytest.fixture
def mock_yf_ticker():
    """Mock yfinance Ticker with complete market data."""
    ticker = Mock()

    ticker.fast_info = Mock()
    ticker.fast_info.last_price = 150.0

    dates = pd.date_range(end=datetime.now(), periods=252, freq="D")
    hist = pd.DataFrame({"Close": np.random.normal(150, 3, 252)}, index=dates)
    ticker.history.return_value = hist

    ticker.options = ["2025-02-15"]

    calls = pd.DataFrame(
        {
            "strike": [145, 150, 155],
            "bid": [6.0, 3.0, 1.0],
            "ask": [6.2, 3.2, 1.1],
            "impliedVolatility": [0.30, 0.28, 0.32],
            "volume": [100, 200, 150],
            "dist": [5.0, 0.0, 5.0],
        }
    )

    puts = pd.DataFrame(
        {
            "strike": [145, 150, 155],
            "bid": [1.0, 3.0, 6.0],
            "ask": [1.1, 3.2, 6.2],
            "impliedVolatility": [0.31, 0.29, 0.33],
            "volume": [100, 200, 150],
            "dist": [5.0, 0.0, 5.0],
        }
    )

    chain = Mock()
    chain.calls = calls
    chain.puts = puts
    ticker.option_chain.return_value = chain

    ticker.info = {"sector": "Technology"}
    ticker.calendar = pd.DataFrame()

    return ticker


@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset singleton between tests."""
    yield
    _reset_default_service()


class TestServiceIntegration:
    """Verify primary get_market_data path works with providers."""

    @patch("variance.market_data.providers.yf.Ticker")
    def test_get_market_data_returns_dict(self, mock_ticker_class, mock_yf_ticker):
        mock_ticker_class.return_value = mock_yf_ticker

        result = get_market_data(["AAPL"])

        assert isinstance(result, dict)
        assert "AAPL" in result

    @patch("variance.market_data.providers.yf.Ticker")
    def test_caching_works_across_multiple_calls(self, mock_ticker_class, mock_yf_ticker):
        mock_ticker_class.return_value = mock_yf_ticker

        result1 = get_market_data(["AAPL"])

        mock_ticker_class.reset_mock()
        result2 = get_market_data(["AAPL"])

        assert mock_ticker_class.call_count == 0
        assert result1["AAPL"]["price"] == result2["AAPL"]["price"]

    def test_default_cache_is_shared(self):
        cache1 = service_module.default_cache
        cache2 = service_module.default_cache
        assert cache1 is cache2


class TestErrorHandling:
    """Verify error handling behavior matches existing expectations."""

    def test_unmapped_symbol_returns_error_dict(self):
        with patch.object(md_settings, "SYMBOL_MAP", {"/ES": "ES=F"}):
            result = get_market_data(["/XX"])

        assert "/XX" in result
        assert "error" in result["/XX"]

    @patch("variance.market_data.providers.yf.Ticker")
    def test_api_failure_returns_error_dict(self, mock_ticker_class):
        mock_ticker_class.side_effect = Exception("API timeout")

        result = get_market_data(["FAIL"])

        assert "FAIL" in result
        assert "error" in result["FAIL"]


class TestPerformanceCharacteristics:
    """Verify that performance characteristics haven't regressed."""

    @patch("variance.market_data.providers.yf.Ticker")
    def test_deduplication_reduces_api_calls(self, mock_ticker_class, mock_yf_ticker):
        mock_ticker_class.return_value = mock_yf_ticker

        service_module.default_cache.get = Mock(return_value=None)

        result = get_market_data(["AAPL"] * 10)

        assert mock_ticker_class.call_count <= 1
        assert len(result) == 1
        assert "AAPL" in result

    @patch("variance.market_data.providers.yf.Ticker")
    def test_concurrent_fetching_for_multiple_symbols(self, mock_ticker_class, mock_yf_ticker):
        mock_ticker_class.return_value = mock_yf_ticker

        service_module.default_cache.get = Mock(return_value=None)

        symbols = ["AAPL", "GOOGL", "MSFT", "TSLA", "NVDA"]
        result = get_market_data(symbols)

        assert len(result) == 5
        for symbol in symbols:
            assert symbol in result


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
