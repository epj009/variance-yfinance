"""
Unit tests for strategy_detector module.
"""

import pytest
import sys
import os

# Add scripts directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from strategy_detector import identify_strategy, map_strategy_to_id


class TestIdentifyStrategy:
    """Test strategy identification logic."""

    def test_identify_single_stock(self):
        legs = [{"Type": "Stock", "Call/Put": "", "Quantity": "100", "Strike Price": "0", "Exp Date": ""}]
        assert identify_strategy(legs) == "Stock"

    def test_identify_long_call(self):
        legs = [{"Type": "Call", "Call/Put": "Call", "Quantity": "1", "Strike Price": "100", "Exp Date": "2024-01-19"}]
        assert identify_strategy(legs) == "Long Call"

    def test_identify_short_put(self):
        legs = [{"Type": "Put", "Call/Put": "Put", "Quantity": "-1", "Strike Price": "95", "Exp Date": "2024-01-19"}]
        assert identify_strategy(legs) == "Short Put"

    def test_identify_strangle(self):
        legs = [
            {"Type": "Call", "Call/Put": "Call", "Quantity": "-1", "Strike Price": "105", "Exp Date": "2024-01-19"},
            {"Type": "Put", "Call/Put": "Put", "Quantity": "-1", "Strike Price": "95", "Exp Date": "2024-01-19"}
        ]
        assert identify_strategy(legs) == "Strangle"

    def test_identify_iron_condor(self):
        legs = [
            {"Type": "Call", "Call/Put": "Call", "Quantity": "-1", "Strike Price": "110", "Exp Date": "2024-01-19"},
            {"Type": "Call", "Call/Put": "Call", "Quantity": "1", "Strike Price": "115", "Exp Date": "2024-01-19"},
            {"Type": "Put", "Call/Put": "Put", "Quantity": "-1", "Strike Price": "90", "Exp Date": "2024-01-19"},
            {"Type": "Put", "Call/Put": "Put", "Quantity": "1", "Strike Price": "85", "Exp Date": "2024-01-19"}
        ]
        assert identify_strategy(legs) == "Iron Condor"

    def test_identify_covered_call(self):
        legs = [
            {"Type": "Stock", "Call/Put": "", "Quantity": "100", "Strike Price": "0", "Exp Date": ""},
            {"Type": "Call", "Call/Put": "Call", "Quantity": "-1", "Strike Price": "105", "Exp Date": "2024-01-19"}
        ]
        assert identify_strategy(legs) == "Covered Call"

    def test_identify_vertical_spread_call(self):
        legs = [
            {"Type": "Call", "Call/Put": "Call", "Quantity": "1", "Strike Price": "100", "Exp Date": "2024-01-19"},
            {"Type": "Call", "Call/Put": "Call", "Quantity": "-1", "Strike Price": "105", "Exp Date": "2024-01-19"}
        ]
        assert identify_strategy(legs) == "Vertical Spread (Call)"


class TestMapStrategyToId:
    """Test strategy name to ID mapping."""

    def test_map_strangle(self):
        assert map_strategy_to_id("Strangle", -100.0) == "short_strangle"

    def test_map_iron_condor(self):
        assert map_strategy_to_id("Iron Condor", -200.0) == "iron_condor"

    def test_map_covered_call(self):
        assert map_strategy_to_id("Covered Call", 5000.0) == "covered_call"

    def test_map_vertical_spread_credit(self):
        assert map_strategy_to_id("Vertical Spread (Call)", -50.0) == "short_call_vertical_spread"

    def test_map_vertical_spread_debit(self):
        assert map_strategy_to_id("Vertical Spread (Put)", 75.0) == "long_put_vertical_spread"

    def test_map_double_diagonal(self):
        assert map_strategy_to_id("Double Diagonal", -150.0) == "double_diagonal"

    def test_map_back_spread(self):
        assert map_strategy_to_id("Back Spread", 50.0) == "back_spread"

    def test_map_unknown_strategy(self):
        assert map_strategy_to_id("Unknown Strategy", 0.0) is None
