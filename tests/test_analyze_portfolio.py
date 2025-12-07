import pytest
import sys
import os
import json

# Add scripts/ folder to path so we can import the modules
sys.path.append(os.path.join(os.path.dirname(__file__), '../scripts'))

from analyze_portfolio import identify_strategy, PortfolioParser
import analyze_portfolio

# Mocking leg data helpers
def make_leg(otype, qty, strike):
    return {
        'Type': 'Option',
        'Call/Put': otype,
        'Quantity': str(qty),
        'Strike Price': str(strike),
        'Exp Date': '2025-01-17',
        'DTE': '45'
    }

def make_stock_leg(qty):
    return {
        'Type': 'Stock',
        'Call/Put': '',
        'Quantity': str(qty),
        'Strike Price': '',
        'Exp Date': '',
        'DTE': ''
    }

# --- Strategy Identification Tests ---

def test_identify_short_strangle():
    legs = [
        make_leg('Call', -1, 110),
        make_leg('Put', -1, 90)
    ]
    assert identify_strategy(legs) == "Strangle"

def test_identify_iron_condor():
    legs = [
        make_leg('Call', -1, 110),
        make_leg('Call', 1, 120),
        make_leg('Put', -1, 90),
        make_leg('Put', 1, 80)
    ]
    assert identify_strategy(legs) == "Iron Condor"

def test_identify_iron_butterfly():
    legs = [
        make_leg('Call', -1, 100),
        make_leg('Put', -1, 100),
        make_leg('Call', 1, 110),
        make_leg('Put', 1, 90)
    ]
    assert identify_strategy(legs) == "Iron Butterfly"

def test_identify_vertical_call_spread():
    legs = [
        make_leg('Call', -1, 100),
        make_leg('Call', 1, 110)
    ]
    assert identify_strategy(legs) == "Vertical Spread (Call)"

def test_identify_covered_call():
    legs = [
        make_stock_leg(100),
        make_leg('Call', -1, 110)
    ]
    assert identify_strategy(legs) == "Covered Call"

def test_identify_jade_lizard():
    # Short Put + Short Call Spread
    legs = [
        make_leg('Put', -1, 90),
        make_leg('Call', -1, 110),
        make_leg('Call', 1, 120)
    ]
    assert identify_strategy(legs) == "Jade Lizard"

def test_identify_single_long_call():
    legs = [
        make_leg('Call', 1, 100)
    ]
    assert identify_strategy(legs) == "Long Call"

def test_identify_unknown_combo():
    # Just a random mix that doesn't fit standard definitions
    legs = [
        make_leg('Call', 1, 100),
        make_leg('Put', 1, 90),
        make_leg('Call', -1, 120) 
    ]
    # Should result in Custom/Combo since it doesn't match strict 2, 3, 4 leg templates perfectly
    # Actually, let's trace logic: 3 legs. 
    # Twisted Sister: Short Call + Put Credit Spread (1 Short Call, 1 Short Put, 1 Long Put)
    # Jade Lizard: Short Put + Call Credit Spread (1 Short Put, 1 Short Call, 1 Long Call)
    # This mock: 1 Long Call, 1 Long Put, 1 Short Call. 
    # It likely falls through to "Custom/Combo"
    assert identify_strategy(legs) == "Custom/Combo"

# --- Parser Normalization Tests ---

def test_normalize_row_tasty_style():
    row = {
        'Symbol': 'XYZ',
        'Type': 'Option',
        'Call/Put': 'CALL',
        'Strike Price': '100',
        'Quantity': '-1',
        'Exp Date': '1/17/25',
        'DTE': '45'
    }
    normalized = PortfolioParser.normalize_row(row)
    assert normalized['Symbol'] == 'XYZ'
    assert normalized['Type'] == 'Option'
    assert normalized['Call/Put'] == 'Call'
    assert normalized['Quantity'] == '-1'


def test_normalize_row_put_lowercase():
    row = {
        'Symbol': 'ABC',
        'Type': 'Option',
        'Call/Put': 'put',
        'Strike Price': '50',
        'Quantity': '1',
        'Exp Date': '1/17/25',
        'DTE': '45'
    }
    normalized = PortfolioParser.normalize_row(row)
    assert normalized['Call/Put'] == 'Put'


# --- Integration-style logic tests with stubbed market data (no network) ---

def test_analyze_portfolio_harvest_action(monkeypatch, tmp_path):
    # Stub market data to avoid network calls
    def fake_get_market_data(symbols):
        return {
            "ABC": {
                "price": 100.0,
                "is_stale": False,
                "vol_bias": 1.2,
                "earnings_date": None,
                "sector": "Technology"
            }
        }
    monkeypatch.setattr(analyze_portfolio, "get_market_data", fake_get_market_data)

    # Deterministic rules for testing
    monkeypatch.setattr(analyze_portfolio, "RULES", {
        "vol_bias_threshold": 0.85,
        "dead_money_vol_bias_threshold": 0.80,
        "dead_money_pl_pct_low": -0.10,
        "dead_money_pl_pct_high": 0.10,
        "low_ivr_threshold": 20,
        "gamma_dte_threshold": 21,
        "profit_harvest_pct": 0.50,
        "earnings_days_threshold": 5,
        "portfolio_delta_long_threshold": 75,
        "portfolio_delta_short_threshold": -50,
        "concentration_risk_pct": 0.25,
        "net_liquidity": 100000,
        "beta_weighted_symbol": "SPY"
    })

    csv_path = tmp_path / "positions.csv"
    csv_path.write_text(
        "Symbol,Type,Quantity,Exp Date,DTE,Strike Price,Call/Put,Underlying Last Price,P/L Open,Cost,Beta Delta,Theta,IV Rank\n"
        "ABC,Option,-1,2025-01-17,30,90,Put,100,50,-100,10,2,30\n"
    )

    report = analyze_portfolio.analyze_portfolio(str(csv_path))
    assert not report.get("error")
    assert len(report["triage_actions"]) == 1
    assert report["triage_actions"][0]["action"] == "🌾 Harvest"
    assert report["portfolio_summary"]["total_beta_delta"] == 10
    assert report["portfolio_summary"]["total_portfolio_theta"] == 2

def test_asset_mix_calculation_equity_heavy(tmp_path, monkeypatch):
    """Test that asset mix correctly identifies equity-heavy portfolios."""
    # Stub market data: AAPL, TSLA, NVDA (Technology = Equity), GLD (Metals = Commodity)
    def mock_get_market_data(symbols):
        return {
            "AAPL": {"price": 150.0, "sector": "Technology", "iv30": 30.0, "hv252": 40.0, "vol_bias": 0.75},
            "TSLA": {"price": 200.0, "sector": "Technology", "iv30": 50.0, "hv252": 60.0, "vol_bias": 0.83},
            "NVDA": {"price": 450.0, "sector": "Technology", "iv30": 45.0, "hv252": 50.0, "vol_bias": 0.90},
            "AMZN": {"price": 140.0, "sector": "Consumer Cyclical", "iv30": 35.0, "hv252": 40.0, "vol_bias": 0.88},
            "GLD": {"price": 180.0, "sector": "Metals", "iv30": 20.0, "hv252": 15.0, "vol_bias": 1.33},
        }
    monkeypatch.setattr(analyze_portfolio, "get_market_data", mock_get_market_data)

    csv_path = tmp_path / "positions.csv"
    csv_path.write_text(
        "Symbol,Type,Quantity,Exp Date,DTE,Strike Price,Call/Put,Underlying Last Price,P/L Open,Cost,Beta Delta,Theta\n"
        "AAPL,Option,-1,2025-01-17,30,150,Put,150,10,-50,5,1\n"
        "TSLA,Option,-1,2025-01-17,30,200,Call,200,10,-50,5,1\n"
        "NVDA,Option,-1,2025-01-17,30,450,Put,450,10,-50,5,1\n"
        "AMZN,Option,-1,2025-01-17,30,140,Put,140,10,-50,5,1\n"
        "GLD,Option,-1,2025-01-17,30,180,Put,180,10,-50,5,1\n"
    )

    report = analyze_portfolio.analyze_portfolio(str(csv_path))
    assert not report.get("error")

    # Check asset mix exists
    assert "asset_mix" in report
    assert len(report["asset_mix"]) > 0

    # Find Equity percentage (4 out of 5 positions = 80%)
    equity_item = next((item for item in report["asset_mix"] if item["asset_class"] == "Equity"), None)
    assert equity_item is not None
    assert equity_item["count"] == 4
    assert equity_item["percentage"] == 0.8

    # Check warning is triggered (> 80%)
    assert report["asset_mix_warning"]["risk"] == False  # Exactly 80%, not > 80%

def test_asset_mix_calculation_equity_warning(tmp_path, monkeypatch):
    """Test that asset mix warning triggers when equity > 80%."""
    def mock_get_market_data(symbols):
        return {
            "AAPL": {"price": 150.0, "sector": "Technology", "iv30": 30.0, "hv252": 40.0, "vol_bias": 0.75},
            "TSLA": {"price": 200.0, "sector": "Technology", "iv30": 50.0, "hv252": 60.0, "vol_bias": 0.83},
            "NVDA": {"price": 450.0, "sector": "Technology", "iv30": 45.0, "hv252": 50.0, "vol_bias": 0.90},
            "AMZN": {"price": 140.0, "sector": "Healthcare", "iv30": 35.0, "hv252": 40.0, "vol_bias": 0.88},
            "MSFT": {"price": 380.0, "sector": "Technology", "iv30": 32.0, "hv252": 38.0, "vol_bias": 0.84},
            "GLD": {"price": 180.0, "sector": "Metals", "iv30": 20.0, "hv252": 15.0, "vol_bias": 1.33},
        }
    monkeypatch.setattr(analyze_portfolio, "get_market_data", mock_get_market_data)

    csv_path = tmp_path / "positions.csv"
    csv_path.write_text(
        "Symbol,Type,Quantity,Exp Date,DTE,Strike Price,Call/Put,Underlying Last Price,P/L Open,Cost,Beta Delta,Theta\n"
        "AAPL,Option,-1,2025-01-17,30,150,Put,150,10,-50,5,1\n"
        "TSLA,Option,-1,2025-01-17,30,200,Call,200,10,-50,5,1\n"
        "NVDA,Option,-1,2025-01-17,30,450,Put,450,10,-50,5,1\n"
        "AMZN,Option,-1,2025-01-17,30,140,Put,140,10,-50,5,1\n"
        "MSFT,Option,-1,2025-01-17,30,380,Put,380,10,-50,5,1\n"
        "GLD,Option,-1,2025-01-17,30,180,Put,180,10,-50,5,1\n"
    )

    report = analyze_portfolio.analyze_portfolio(str(csv_path))
    assert not report.get("error")

    # 5 Equity out of 6 = 83.33% > 80%
    equity_item = next((item for item in report["asset_mix"] if item["asset_class"] == "Equity"), None)
    assert equity_item is not None
    assert equity_item["count"] == 5
    assert equity_item["percentage"] > 0.80

    # Check warning is triggered
    assert report["asset_mix_warning"]["risk"] == True
    assert "83%" in report["asset_mix_warning"]["details"] or "Equity" in report["asset_mix_warning"]["details"]

def test_asset_mix_diversified(tmp_path, monkeypatch):
    """Test that diversified portfolios don't trigger warnings."""
    def mock_get_market_data(symbols):
        return {
            "AAPL": {"price": 150.0, "sector": "Technology", "iv30": 30.0, "hv252": 40.0, "vol_bias": 0.75},
            "GLD": {"price": 180.0, "sector": "Metals", "iv30": 20.0, "hv252": 15.0, "vol_bias": 1.33},
            "/CL": {"price": 70.0, "sector": "Energy", "iv30": 40.0, "hv252": 35.0, "vol_bias": 1.14},
            "/6E": {"price": 1.1, "sector": "Currencies", "iv30": 10.0, "hv252": 8.0, "vol_bias": 1.25},
            "TLT": {"price": 95.0, "sector": "Fixed Income", "iv30": 12.0, "hv252": 10.0, "vol_bias": 1.20},
        }
    monkeypatch.setattr(analyze_portfolio, "get_market_data", mock_get_market_data)

    csv_path = tmp_path / "positions.csv"
    csv_path.write_text(
        "Symbol,Type,Quantity,Exp Date,DTE,Strike Price,Call/Put,Underlying Last Price,P/L Open,Cost,Beta Delta,Theta\n"
        "AAPL,Option,-1,2025-01-17,30,150,Put,150,10,-50,5,1\n"
        "GLD,Option,-1,2025-01-17,30,180,Put,180,10,-50,5,1\n"
        "/CL,Option,-1,2025-01-17,30,70,Call,70,10,-50,5,1\n"
        "/6E,Option,-1,2025-01-17,30,1.1,Put,1.1,10,-50,5,1\n"
        "TLT,Option,-1,2025-01-17,30,95,Put,95,10,-50,5,1\n"
    )

    report = analyze_portfolio.analyze_portfolio(str(csv_path))
    assert not report.get("error")

    # Should have 4 asset classes (Equity, Commodity x2, FX, Fixed Income)
    # Note: GLD (Metals) and /CL (Energy) both map to Commodity
    assert len(report["asset_mix"]) == 4

    # Find each asset class
    asset_classes_found = {item["asset_class"] for item in report["asset_mix"]}
    assert "Equity" in asset_classes_found
    assert "Commodity" in asset_classes_found
    assert "FX" in asset_classes_found
    assert "Fixed Income" in asset_classes_found

    # No single asset class should be > 80%
    for item in report["asset_mix"]:
        assert item["percentage"] <= 0.80

    # Commodity should be 40% (2 out of 5 positions)
    commodity_item = next((item for item in report["asset_mix"] if item["asset_class"] == "Commodity"), None)
    assert commodity_item is not None
    assert commodity_item["count"] == 2
    assert commodity_item["percentage"] == 0.4

    # Warning should NOT be triggered
    assert report["asset_mix_warning"]["risk"] == False
