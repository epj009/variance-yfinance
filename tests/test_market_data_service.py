from unittest.mock import Mock, patch

import pytest

from variance.market_data import service as service_module
from variance.market_data.cache import MarketCache
from variance.market_data.service import MarketDataService


@pytest.fixture
def test_cache(tmp_path):
    db_path = tmp_path / "test_service_cache.db"
    cache = MarketCache(str(db_path))
    yield cache
    cache.close_all()


class TestMarketDataService:
    @patch("variance.market_data.providers.yf.Ticker")
    def test_service_checks_cache_first(self, mock_ticker, test_cache):
        service_module.load_runtime_config = Mock(return_value={"tastytrade": {"enabled": False}})
        service = MarketDataService(cache=test_cache, market_open_fn=lambda: True)
        data = {"price": 100.0, "iv": 20.0, "hv252": 15.0}
        test_cache.set("md_AAPL", data, 3600)
        result = service.get_market_data(["AAPL"])
        assert result["AAPL"]["price"] == 100.0
        assert mock_ticker.call_count == 0

    @patch("variance.market_data.providers.yf.Ticker")
    def test_service_fetches_missing(self, mock_ticker, test_cache):
        service_module.load_runtime_config = Mock(return_value={"tastytrade": {"enabled": False}})
        service = MarketDataService(cache=test_cache, market_open_fn=lambda: True)
        # Should call Ticker because cache is empty
        service.get_market_data(["AAPL"])
        assert mock_ticker.call_count == 1
