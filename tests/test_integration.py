"""
Integration tests for the full portfolio analysis pipeline.
"""

import json
import os

import pytest

from variance.analyze_portfolio import analyze_portfolio
from variance.market_data.service import MarketDataFactory


class TestAnalyzePortfolioIntegration:
    """Test the full portfolio analysis pipeline."""

    @pytest.fixture
    def mock_provider(self, mock_market_provider):
        """Standard mock data for integration tests."""
        fake_data = {
            "SPY": {
                "price": 450.0,
                "iv": 15.0,
                "hv252": 14.0,
                "vrp_structural": 1.07,
                "sector": "Index",
            },
            "AAPL": {
                "price": 150.0,
                "iv": 30.0,
                "hv252": 25.0,
                "vrp_structural": 1.2,
                "sector": "Technology",
            },
            "TSLA": {
                "price": 200.0,
                "iv": 50.0,
                "hv252": 45.0,
                "vrp_structural": 1.1,
                "sector": "Technology",
            },
            "IWM": {
                "price": 200.0,
                "iv": 20.0,
                "hv252": 18.0,
                "vrp_structural": 1.1,
                "sector": "Index",
            },
            "DIA": {
                "price": 350.0,
                "iv": 12.0,
                "hv252": 11.0,
                "vrp_structural": 1.09,
                "sector": "Index",
            },
            "QQQ": {
                "price": 380.0,
                "iv": 18.0,
                "hv252": 16.0,
                "vrp_structural": 1.12,
                "sector": "Index",
            },
            "GLD": {
                "price": 180.0,
                "iv": 15.0,
                "hv252": 12.0,
                "vrp_structural": 1.25,
                "sector": "Metals",
            },
            "NVDA": {
                "price": 480.0,
                "iv": 45.0,
                "hv252": 40.0,
                "vrp_structural": 1.12,
                "sector": "Technology",
            },
        }
        return mock_market_provider(fake_data)

    def test_analyze_portfolio_with_sample_csv(self, monkeypatch, mock_provider):
        """Test that the analyzer runs without errors on sample CSV."""
        monkeypatch.setattr(
            MarketDataFactory, "get_provider", lambda type="yfinance": mock_provider
        )

        csv_path = os.path.join(os.path.dirname(__file__), "..", "util", "sample_positions.csv")

        # Skip if sample file doesn't exist
        if not os.path.exists(csv_path):
            pytest.skip(f"Sample CSV not found at {csv_path}")

        result = analyze_portfolio(csv_path)

        # Basic structure validation
        assert isinstance(result, dict)
        assert "analysis_time" in result
        assert "triage_actions" in result
        assert "portfolio_summary" in result
        assert "error" not in result

    def test_analyze_portfolio_returns_valid_json(self, monkeypatch, mock_provider):
        """Test that the output can be serialized to JSON."""
        monkeypatch.setattr(
            MarketDataFactory, "get_provider", lambda type="yfinance": mock_provider
        )

        csv_path = os.path.join(os.path.dirname(__file__), "..", "util", "sample_positions.csv")

        if not os.path.exists(csv_path):
            pytest.skip(f"Sample CSV not found at {csv_path}")

        result = analyze_portfolio(csv_path)

        # Should be JSON serializable
        try:
            json_str = json.dumps(result, indent=2)
            assert len(json_str) > 0
        except (TypeError, ValueError) as e:
            pytest.fail(f"Result is not JSON serializable: {e}")

    def test_analyze_portfolio_missing_file_raises_exception(self):
        """Test error handling for missing CSV file."""
        from variance.portfolio_parser import PortfolioParser

        # Parser should raise FileNotFoundError for missing files
        with pytest.raises(FileNotFoundError):
            PortfolioParser.parse("/nonexistent/file.csv")
