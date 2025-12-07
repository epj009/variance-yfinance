import sys
import os
import json
import pytest

# Add scripts/ folder to path so we can import the modules
sys.path.append(os.path.join(os.path.dirname(__file__), '../scripts'))

import vol_screener


def test_screen_volatility_filters_and_excludes(monkeypatch, tmp_path):
    # Prepare a fake watchlist
    watchlist = tmp_path / "watchlist.csv"
    watchlist.write_text("Symbol\nABC\nDEF\nGHI\n")

    # Stub market data to avoid network calls
    fake_data = {
        "ABC": {"price": 50, "iv30": 30, "hv252": 20, "vol_bias": 1.5, "earnings_date": None, "sector": "Tech"},
        "DEF": {"price": 40, "iv30": 25, "hv252": 15, "vol_bias": 1.2, "earnings_date": None, "sector": "Energy"},
        "GHI": {"price": 30, "iv30": 10, "hv252": 20, "vol_bias": 0.5, "earnings_date": None, "sector": "Finance"},
    }

    def fake_get_market_data(symbols):
        return {sym: fake_data[sym] for sym in symbols}

    monkeypatch.setattr(vol_screener, "get_market_data", fake_get_market_data)
    monkeypatch.setattr(vol_screener, "WATCHLIST_PATH", str(watchlist))
    monkeypatch.setattr(vol_screener, "RULES", {
        "vol_bias_threshold": 0.8,
        "earnings_days_threshold": 5,
        "bats_efficiency_min_price": 15,
        "bats_efficiency_max_price": 75,
        "bats_efficiency_vol_bias": 1.0
    })

    report = vol_screener.screen_volatility(show_all=False, exclude_sectors=["Energy"])
    candidates = report["candidates"]
    summary = report["summary"]

    assert len(candidates) == 1
    assert candidates[0]["Symbol"] == "ABC"
    assert "🦇 Bats Efficiency Zone" in candidates[0]["Status Icons"]

    # DEF excluded by sector, GHI skipped by low bias
    assert summary["sector_skipped_count"] == 1
    assert summary["low_bias_skipped_count"] == 1

def test_screen_volatility_include_asset_classes(monkeypatch, tmp_path):
    """Test that --include-asset-classes filters correctly."""
    # Prepare fake watchlist
    watchlist = tmp_path / "watchlist.csv"
    watchlist.write_text("Symbol\nAAPL\nGLD\n/CL\n/6E\n")

    # Stub market data with different sectors -> asset classes
    fake_data = {
        "AAPL": {"price": 150, "iv30": 30, "hv252": 40, "vol_bias": 0.90, "earnings_date": None, "sector": "Technology"},  # Equity
        "GLD": {"price": 180, "iv30": 20, "hv252": 15, "vol_bias": 1.33, "earnings_date": None, "sector": "Metals"},  # Commodity
        "/CL": {"price": 70, "iv30": 40, "hv252": 35, "vol_bias": 1.14, "earnings_date": None, "sector": "Energy"},  # Commodity
        "/6E": {"price": 1.1, "iv30": 10, "hv252": 8, "vol_bias": 1.25, "earnings_date": None, "sector": "Currencies"},  # FX
    }

    def fake_get_market_data(symbols):
        return {sym: fake_data[sym] for sym in symbols}

    monkeypatch.setattr(vol_screener, "get_market_data", fake_get_market_data)
    monkeypatch.setattr(vol_screener, "WATCHLIST_PATH", str(watchlist))
    monkeypatch.setattr(vol_screener, "RULES", {
        "vol_bias_threshold": 0.85,
        "earnings_days_threshold": 5,
        "bats_efficiency_min_price": 15,
        "bats_efficiency_max_price": 75,
        "bats_efficiency_vol_bias": 1.0
    })

    # Test: Include only Commodity and FX
    report = vol_screener.screen_volatility(show_all=True, include_asset_classes=["Commodity", "FX"])
    candidates = report["candidates"]
    summary = report["summary"]

    # Should get GLD, /CL, /6E (3 total), exclude AAPL (Equity)
    assert len(candidates) == 3
    symbols = [c["Symbol"] for c in candidates]
    assert "GLD" in symbols
    assert "/CL" in symbols
    assert "/6E" in symbols
    assert "AAPL" not in symbols

    # Check asset class is in candidate data
    for c in candidates:
        assert "Asset Class" in c
        assert c["Asset Class"] in ["Commodity", "FX"]

    # Check summary
    assert summary["asset_class_skipped_count"] == 1  # AAPL excluded

def test_screen_volatility_exclude_asset_classes(monkeypatch, tmp_path):
    """Test that --exclude-asset-classes filters correctly."""
    watchlist = tmp_path / "watchlist.csv"
    watchlist.write_text("Symbol\nAAPL\nTSLA\nGLD\n/CL\n")

    fake_data = {
        "AAPL": {"price": 150, "iv30": 30, "hv252": 40, "vol_bias": 0.90, "earnings_date": None, "sector": "Technology"},  # Equity
        "TSLA": {"price": 200, "iv30": 50, "hv252": 60, "vol_bias": 0.90, "earnings_date": None, "sector": "Technology"},  # Equity
        "GLD": {"price": 180, "iv30": 20, "hv252": 15, "vol_bias": 1.33, "earnings_date": None, "sector": "Metals"},  # Commodity
        "/CL": {"price": 70, "iv30": 40, "hv252": 35, "vol_bias": 1.14, "earnings_date": None, "sector": "Energy"},  # Commodity
    }

    def fake_get_market_data(symbols):
        return {sym: fake_data[sym] for sym in symbols}

    monkeypatch.setattr(vol_screener, "get_market_data", fake_get_market_data)
    monkeypatch.setattr(vol_screener, "WATCHLIST_PATH", str(watchlist))
    monkeypatch.setattr(vol_screener, "RULES", {
        "vol_bias_threshold": 0.85,
        "earnings_days_threshold": 5,
        "bats_efficiency_min_price": 15,
        "bats_efficiency_max_price": 75,
        "bats_efficiency_vol_bias": 1.0
    })

    # Test: Exclude Equity
    report = vol_screener.screen_volatility(show_all=True, exclude_asset_classes=["Equity"])
    candidates = report["candidates"]
    summary = report["summary"]

    # Should get GLD, /CL (2 total), exclude AAPL and TSLA
    assert len(candidates) == 2
    symbols = [c["Symbol"] for c in candidates]
    assert "GLD" in symbols
    assert "/CL" in symbols
    assert "AAPL" not in symbols
    assert "TSLA" not in symbols

    # All candidates should be Commodity
    for c in candidates:
        assert c["Asset Class"] == "Commodity"

    # Check summary
    assert summary["asset_class_skipped_count"] == 2  # AAPL and TSLA excluded
