"""
Unit tests for strategy_detector module.
"""

import pytest
import sys
import os

# Add scripts directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from strategy_detector import identify_strategy, map_strategy_to_id, cluster_strategies


def make_leg(
    symbol="ABC",
    option_type="Call",
    qty=1,
    strike=100,
    exp="2024-01-19",
    dte="45",
    underlying_price="100",
    delta=None
):
    leg = {
        "Symbol": symbol,
        "Type": option_type,
        "Call/Put": option_type if option_type in {"Call", "Put"} else "",
        "Quantity": str(qty),
        "Strike Price": str(strike),
        "Exp Date": exp,
        "DTE": str(dte),
        "Underlying Last Price": str(underlying_price),
        "Delta": "" if delta is None else str(delta),
    }
    return leg


def make_stock_leg(symbol="ABC", qty=100, underlying_price="100"):
    return {
        "Symbol": symbol,
        "Type": "Stock",
        "Call/Put": "",
        "Quantity": str(qty),
        "Strike Price": "0",
        "Exp Date": "",
        "DTE": "",
        "Underlying Last Price": str(underlying_price),
    }


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
        assert identify_strategy(legs) == "Short Strangle"

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


class TestClusterStrategies:
    """Test strategy clustering logic."""

    def test_cluster_separates_multiple_verticals(self):
        positions = [
            {"Symbol": "ABC", "Type": "Call", "Call/Put": "Call", "Quantity": "1", "Strike Price": "100", "Exp Date": "2024-01-19"},
            {"Symbol": "ABC", "Type": "Call", "Call/Put": "Call", "Quantity": "-1", "Strike Price": "105", "Exp Date": "2024-01-19"},
            {"Symbol": "ABC", "Type": "Call", "Call/Put": "Call", "Quantity": "1", "Strike Price": "110", "Exp Date": "2024-01-19"},
            {"Symbol": "ABC", "Type": "Call", "Call/Put": "Call", "Quantity": "-1", "Strike Price": "115", "Exp Date": "2024-01-19"},
        ]
        clusters = cluster_strategies(positions)
        assert len(clusters) == 2
        for cluster in clusters:
            assert identify_strategy(cluster) == "Vertical Spread (Call)"

    def test_cluster_builds_iron_condor(self):
        positions = [
            {"Symbol": "XYZ", "Type": "Call", "Call/Put": "Call", "Quantity": "-1", "Strike Price": "110", "Exp Date": "2024-01-19"},
            {"Symbol": "XYZ", "Type": "Call", "Call/Put": "Call", "Quantity": "1", "Strike Price": "115", "Exp Date": "2024-01-19"},
            {"Symbol": "XYZ", "Type": "Put", "Call/Put": "Put", "Quantity": "-1", "Strike Price": "90", "Exp Date": "2024-01-19"},
            {"Symbol": "XYZ", "Type": "Put", "Call/Put": "Put", "Quantity": "1", "Strike Price": "85", "Exp Date": "2024-01-19"},
        ]
        clusters = cluster_strategies(positions)
        assert len(clusters) == 1
        assert identify_strategy(clusters[0]) == "Iron Condor"

    def test_cluster_builds_butterfly(self):
        positions = [
            {"Symbol": "XYZ", "Type": "Call", "Call/Put": "Call", "Quantity": "1", "Strike Price": "100", "Exp Date": "2024-01-19"},
            {"Symbol": "XYZ", "Type": "Call", "Call/Put": "Call", "Quantity": "-2", "Strike Price": "105", "Exp Date": "2024-01-19"},
            {"Symbol": "XYZ", "Type": "Call", "Call/Put": "Call", "Quantity": "1", "Strike Price": "110", "Exp Date": "2024-01-19"},
        ]
        clusters = cluster_strategies(positions)
        assert len(clusters) == 1
        assert identify_strategy(clusters[0]) == "Call Butterfly"

    def test_cluster_builds_strangle(self):
        positions = [
            make_leg(symbol="XYZ", option_type="Call", qty=-1, strike=110, exp="2024-01-19"),
            make_leg(symbol="XYZ", option_type="Put", qty=-1, strike=90, exp="2024-01-19"),
        ]
        clusters = cluster_strategies(positions)
        assert len(clusters) == 1
        assert identify_strategy(clusters[0]) == "Short Strangle"

    def test_cluster_builds_straddle(self):
        positions = [
            make_leg(symbol="XYZ", option_type="Call", qty=-1, strike=100, exp="2024-01-19"),
            make_leg(symbol="XYZ", option_type="Put", qty=-1, strike=100, exp="2024-01-19"),
        ]
        clusters = cluster_strategies(positions)
        assert len(clusters) == 1
        assert identify_strategy(clusters[0]) == "Short Straddle"


@pytest.mark.parametrize(
    "legs, net_cost, expected_id",
    [
        # Covered
        ([make_stock_leg(), make_leg(option_type="Call", qty=-1, strike=105)], -50.0, "covered_call"),
        ([make_stock_leg(), make_leg(option_type="Put", qty=-1, strike=95)], -50.0, "covered_put"),
        # Verticals
        ([make_leg(option_type="Call", qty=1, strike=100), make_leg(option_type="Call", qty=-1, strike=105)], 200.0, "long_call_vertical_spread"),
        ([make_leg(option_type="Call", qty=-1, strike=100), make_leg(option_type="Call", qty=1, strike=105)], -150.0, "short_call_vertical_spread"),
        ([make_leg(option_type="Put", qty=1, strike=100), make_leg(option_type="Put", qty=-1, strike=95)], 200.0, "long_put_vertical_spread"),
        ([make_leg(option_type="Put", qty=-1, strike=100), make_leg(option_type="Put", qty=1, strike=95)], -150.0, "short_put_vertical_spread"),
        # Calendars
        ([make_leg(option_type="Call", qty=-1, strike=100, exp="2024-01-19", dte="30"), make_leg(option_type="Call", qty=1, strike=100, exp="2024-02-16", dte="60")], 50.0, "call_calendar_spread"),
        ([make_leg(option_type="Put", qty=-1, strike=100, exp="2024-01-19", dte="30"), make_leg(option_type="Put", qty=1, strike=100, exp="2024-02-16", dte="60")], 50.0, "put_calendar_spread"),
        # PMCC/PMCP
        ([make_leg(option_type="Call", qty=1, strike=90, exp="2024-03-15", dte="90", underlying_price="100", delta=0.7), make_leg(option_type="Call", qty=-1, strike=110, exp="2024-02-16", dte="45", underlying_price="100", delta=0.3)], 200.0, "poor_mans_covered_call"),
        ([make_leg(option_type="Put", qty=1, strike=110, exp="2024-03-15", dte="90", underlying_price="100", delta=-0.7), make_leg(option_type="Put", qty=-1, strike=90, exp="2024-02-16", dte="45", underlying_price="100", delta=-0.3)], 200.0, "poor_mans_covered_put"),
        # Butterflies
        ([make_leg(option_type="Call", qty=1, strike=100), make_leg(option_type="Call", qty=-2, strike=105), make_leg(option_type="Call", qty=1, strike=110)], 100.0, "call_butterfly"),
        ([make_leg(option_type="Put", qty=1, strike=110), make_leg(option_type="Put", qty=-2, strike=105), make_leg(option_type="Put", qty=1, strike=100)], 100.0, "put_butterfly"),
        ([make_leg(option_type="Call", qty=1, strike=100), make_leg(option_type="Call", qty=-2, strike=105), make_leg(option_type="Call", qty=1, strike=112)], 50.0, "call_broken_wing_butterfly"),
        ([make_leg(option_type="Put", qty=1, strike=112), make_leg(option_type="Put", qty=-2, strike=105), make_leg(option_type="Put", qty=1, strike=100)], 50.0, "put_broken_wing_butterfly"),
        ([make_leg(option_type="Call", qty=1, strike=95), make_leg(option_type="Call", qty=-1, strike=100), make_leg(option_type="Call", qty=-1, strike=105), make_leg(option_type="Call", qty=1, strike=115)], 50.0, "call_broken_heart_butterfly"),
        ([make_leg(option_type="Put", qty=1, strike=115), make_leg(option_type="Put", qty=-1, strike=110), make_leg(option_type="Put", qty=-1, strike=105), make_leg(option_type="Put", qty=1, strike=95)], 50.0, "put_broken_heart_butterfly"),
        # ZEBRA / Front Ratio
        ([make_leg(option_type="Call", qty=2, strike=90), make_leg(option_type="Call", qty=-1, strike=100)], 50.0, "call_zebra"),
        ([make_leg(option_type="Put", qty=2, strike=110), make_leg(option_type="Put", qty=-1, strike=100)], 50.0, "put_zebra"),
        ([make_leg(option_type="Call", qty=1, strike=90), make_leg(option_type="Call", qty=-2, strike=100)], 50.0, "call_front_ratio_spread"),
        ([make_leg(option_type="Put", qty=1, strike=110), make_leg(option_type="Put", qty=-2, strike=100)], 50.0, "put_front_ratio_spread"),
        # Strangles / Straddles
        ([make_leg(option_type="Call", qty=-1, strike=110), make_leg(option_type="Put", qty=-1, strike=90)], -100.0, "short_strangle"),
        ([make_leg(option_type="Call", qty=-1, strike=100), make_leg(option_type="Put", qty=-1, strike=100)], -100.0, "short_straddle"),
        # Condors / Fly
        ([make_leg(option_type="Call", qty=-1, strike=110), make_leg(option_type="Call", qty=1, strike=115), make_leg(option_type="Put", qty=-1, strike=90), make_leg(option_type="Put", qty=1, strike=85)], -100.0, "iron_condor"),
        ([make_leg(option_type="Call", qty=-1, strike=110), make_leg(option_type="Call", qty=1, strike=118), make_leg(option_type="Put", qty=-1, strike=90), make_leg(option_type="Put", qty=1, strike=85)], -100.0, "dynamic_width_iron_condor"),
        ([make_leg(option_type="Call", qty=-1, strike=100), make_leg(option_type="Call", qty=1, strike=110), make_leg(option_type="Put", qty=-1, strike=100), make_leg(option_type="Put", qty=1, strike=90)], -100.0, "iron_fly"),
        # Naked
        ([make_leg(option_type="Put", qty=-1, strike=95)], -50.0, "short_naked_put"),
        ([make_leg(option_type="Call", qty=-1, strike=105)], -50.0, "short_naked_call"),
        # Lizard family
        ([make_leg(option_type="Put", qty=-1, strike=95, underlying_price="100"), make_leg(option_type="Call", qty=-1, strike=110, underlying_price="100"), make_leg(option_type="Call", qty=1, strike=115, underlying_price="100")], -100.0, "jade_lizard"),
        ([make_leg(option_type="Put", qty=-1, strike=100, underlying_price="100"), make_leg(option_type="Call", qty=-1, strike=110, underlying_price="100"), make_leg(option_type="Call", qty=1, strike=115, underlying_price="100")], -100.0, "big_lizard"),
        ([make_leg(option_type="Call", qty=-1, strike=110, underlying_price="100"), make_leg(option_type="Put", qty=-1, strike=95, underlying_price="100"), make_leg(option_type="Put", qty=1, strike=90, underlying_price="100")], -100.0, "reverse_jade_lizard"),
        ([make_leg(option_type="Call", qty=-1, strike=100, underlying_price="100"), make_leg(option_type="Put", qty=-1, strike=95, underlying_price="100"), make_leg(option_type="Put", qty=1, strike=90, underlying_price="100")], -100.0, "reverse_big_lizard"),
    ],
)
def test_strategy_coverage(legs, net_cost, expected_id):
    name = identify_strategy(legs)
    strategy_id = map_strategy_to_id(name, net_cost)
    assert strategy_id == expected_id
