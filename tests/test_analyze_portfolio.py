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
