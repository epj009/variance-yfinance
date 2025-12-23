from unittest.mock import patch

import pytest

from variance.get_market_data import MarketCache, MarketDataService


@pytest.fixture
def test_cache(tmp_path):
    db_path = tmp_path / "test_service_cache.db"
    return MarketCache(str(db_path))

class TestMarketDataService:
    @patch('variance.get_market_data.yf.Ticker')
    def test_service_checks_cache_first(self, mock_ticker, test_cache):
        service = MarketDataService(cache=test_cache)
        data = {"price": 100.0, "iv": 20.0, "hv252": 15.0}
        test_cache.set("md_AAPL", data, 3600)
        result = service.get_market_data(['AAPL'])
        assert result['AAPL']['price'] == 100.0
        assert mock_ticker.call_count == 0

    @patch('variance.get_market_data.yf.Ticker')
    def test_service_fetches_missing(self, mock_ticker, test_cache):
        service = MarketDataService(cache=test_cache)
        # Should call Ticker because cache is empty
        service.get_market_data(['AAPL'])
        assert mock_ticker.call_count == 1
