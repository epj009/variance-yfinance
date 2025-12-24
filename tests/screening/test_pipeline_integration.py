"""
Integration tests for the Screening Pipeline.
"""

from unittest.mock import patch

from variance.config_loader import load_config_bundle
from variance.screening.pipeline import ScreeningPipeline
from variance.vol_screener import ScreenerConfig


def test_pipeline_execution():
    # Arrange
    config = ScreenerConfig(limit=2)
    bundle = load_config_bundle(strict=False)

    # Mock symbols and data to avoid API calls
    with patch("variance.screening.steps.load.load_watchlist", return_value=["AAPL", "TSLA"]):
        with patch("variance.screening.steps.fetch.fetch_market_data") as mock_fetch:
            mock_fetch.return_value = {
                "AAPL": {
                    "price": 150,
                    "iv": 30,
                    "hv20": 20,
                    "hv252": 25,
                    "vrp_structural": 1.2,
                    "sector": "Tech",
                },
                "TSLA": {
                    "price": 200,
                    "iv": 50,
                    "hv20": 40,
                    "hv252": 45,
                    "vrp_structural": 1.1,
                    "sector": "Auto",
                },
            }

            pipeline = ScreeningPipeline(config, bundle)
            report = pipeline.execute()

            # Assert
            assert "candidates" in report
            assert len(report["candidates"]) == 2
            assert "summary" in report
            assert report["meta"]["profile"] == "default"

            # Verify enrichment was applied
            assert "Score" in report["candidates"][0]
            assert "Signal" in report["candidates"][0]
