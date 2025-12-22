import sys
import os
import json
import pytest

# Add scripts/ folder to path so we can import the modules
sys.path.append(os.path.join(os.path.dirname(__file__), '../scripts'))

import vol_screener


def make_config_bundle(trading_rules, system_config, market_config=None):
    return {
        "trading_rules": trading_rules,
        "system_config": system_config,
        "market_config": market_config or {},
        "screener_profiles": {},
        "strategies": {}
    }


def test_screen_volatility_filters_and_excludes(monkeypatch, tmp_path):
    # Prepare a fake watchlist
    watchlist = tmp_path / "watchlist.csv"
    watchlist.write_text("Symbol\nABC\nDEF\nGHI\n")

    # Stub market data to avoid network calls
    fake_data = {
        "ABC": {"price": 50, "iv": 30, "hv252": 20, "hv20": 18, "vrp_structural": 1.5, "earnings_date": None, "sector": "Tech", "atm_volume": 600},
        "DEF": {"price": 40, "iv": 25, "hv252": 15, "hv20": 14, "vrp_structural": 1.2, "earnings_date": None, "sector": "Energy", "atm_volume": 600},
        "GHI": {"price": 30, "iv": 10, "hv252": 20, "hv20": 19, "vrp_structural": 0.5, "earnings_date": None, "sector": "Finance", "atm_volume": 600},
    }

    def fake_get_market_data(symbols):
        return {sym: fake_data[sym] for sym in symbols}

    monkeypatch.setattr(vol_screener, "get_market_data", fake_get_market_data)
    config_bundle = make_config_bundle(
        trading_rules={
            "vrp_structural_threshold": 0.8,
            "vrp_structural_rich_threshold": 1.0,
            "earnings_days_threshold": 5,
            "bats_efficiency_min_price": 15,
            "bats_efficiency_max_price": 75,
            "bats_efficiency_vrp_structural": 1.0,
            "min_atm_volume": 500,
            "max_slippage_pct": 0.05
        },
        system_config={
            "watchlist_path": str(watchlist),
            "fallback_symbols": ["SPY", "QQQ", "IWM"]
        },
        market_config={"FAMILY_MAP": {}},
    )

    config = vol_screener.ScreenerConfig(exclude_sectors=["Energy"])
    report = vol_screener.screen_volatility(config, config_bundle=config_bundle)
    candidates = report["candidates"]
    summary = report["summary"]

    assert len(candidates) == 1
    assert candidates[0]["Symbol"] == "ABC"
    assert candidates[0]["is_bats_efficient"] == True
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
        "AAPL": {"price": 150, "iv": 30, "hv252": 40, "hv20": 35, "vrp_structural": 0.90, "earnings_date": None, "sector": "Technology", "atm_volume": 600},  # Equity
        "GLD": {"price": 180, "iv": 20, "hv252": 15, "hv20": 14, "vrp_structural": 1.33, "earnings_date": None, "sector": "Metals", "atm_volume": 600},  # Commodity
        "/CL": {"price": 70, "iv": 40, "hv252": 35, "hv20": 30, "vrp_structural": 1.14, "earnings_date": None, "sector": "Energy", "atm_volume": 600},  # Commodity
        "/6E": {"price": 1.1, "iv": 10, "hv252": 8, "hv20": 7.5, "vrp_structural": 1.25, "earnings_date": None, "sector": "Currencies", "atm_volume": 600},  # FX
    }

    def fake_get_market_data(symbols):
        return {sym: fake_data[sym] for sym in symbols}

    monkeypatch.setattr(vol_screener, "get_market_data", fake_get_market_data)
    config_bundle = make_config_bundle(
        trading_rules={
            "vrp_structural_threshold": 0.85,
            "vrp_structural_rich_threshold": 1.0,
            "earnings_days_threshold": 5,
            "bats_efficiency_min_price": 15,
            "bats_efficiency_max_price": 75,
            "bats_efficiency_vrp_structural": 1.0,
            "min_atm_volume": 500,
            "max_slippage_pct": 0.05
        },
        system_config={
            "watchlist_path": str(watchlist),
            "fallback_symbols": ["SPY", "QQQ", "IWM"]
        },
        market_config={"FAMILY_MAP": {}},
    )

    # Test: Include only Commodity and FX
    config = vol_screener.ScreenerConfig(
        min_vrp_structural=0.0,
        include_asset_classes=["Commodity", "FX"]
    )
    report = vol_screener.screen_volatility(config, config_bundle=config_bundle)
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
        "AAPL": {"price": 150, "iv": 30, "hv252": 40, "hv20": 35, "vrp_structural": 0.90, "earnings_date": None, "sector": "Technology", "atm_volume": 600},  # Equity
        "TSLA": {"price": 200, "iv": 50, "hv252": 60, "hv20": 55, "vrp_structural": 0.90, "earnings_date": None, "sector": "Technology", "atm_volume": 600},  # Equity
        "GLD": {"price": 180, "iv": 20, "hv252": 15, "hv20": 14, "vrp_structural": 1.33, "earnings_date": None, "sector": "Metals", "atm_volume": 600},  # Commodity
        "/CL": {"price": 70, "iv": 40, "hv252": 35, "hv20": 30, "vrp_structural": 1.14, "earnings_date": None, "sector": "Energy", "atm_volume": 600},  # Commodity
    }

    def fake_get_market_data(symbols):
        return {sym: fake_data[sym] for sym in symbols}

    monkeypatch.setattr(vol_screener, "get_market_data", fake_get_market_data)
    config_bundle = make_config_bundle(
        trading_rules={
            "vrp_structural_threshold": 0.85,
            "vrp_structural_rich_threshold": 1.0,
            "earnings_days_threshold": 5,
            "bats_efficiency_min_price": 15,
            "bats_efficiency_max_price": 75,
            "bats_efficiency_vrp_structural": 1.0,
            "min_atm_volume": 500,
            "max_slippage_pct": 0.05
        },
        system_config={
            "watchlist_path": str(watchlist),
            "fallback_symbols": ["SPY", "QQQ", "IWM"]
        },
        market_config={"FAMILY_MAP": {}},
    )

    # Test: Exclude Equity
    config = vol_screener.ScreenerConfig(
        min_vrp_structural=0.0,
        exclude_asset_classes=["Equity"]
    )
    report = vol_screener.screen_volatility(config, config_bundle=config_bundle)
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
