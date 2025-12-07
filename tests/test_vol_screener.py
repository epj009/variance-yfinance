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
