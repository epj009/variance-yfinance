import pytest
import sys
import os
import json

# Add scripts/ folder to path so we can import the modules
sys.path.append(os.path.join(os.path.dirname(__file__), '../scripts'))

from analyze_portfolio import identify_strategy, PortfolioParser

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
