"""
Unit tests for Strategy ID Mapping.
"""

from variance.classification.mapping import map_strategy_to_id


def test_direct_mapping():
    assert map_strategy_to_id("Short Strangle", -100) == "short_strangle"
    assert map_strategy_to_id("Iron Condor", -200) == "iron_condor"
    assert map_strategy_to_id("Covered Call", -500) == "covered_call"


def test_conditional_mapping_verticals():
    # Call Credit Spread (Short Vertical)
    assert map_strategy_to_id("Vertical Spread (Call)", -50) == "short_call_vertical_spread"
    # Call Debit Spread (Long Vertical)
    assert map_strategy_to_id("Vertical Spread (Call)", 50) == "long_call_vertical_spread"

    # Put Credit Spread
    assert map_strategy_to_id("Vertical Spread (Put)", -50) == "short_put_vertical_spread"
    # Put Debit Spread
    assert map_strategy_to_id("Vertical Spread (Put)", 50) == "long_put_vertical_spread"


def test_conditional_mapping_diagonals():
    assert map_strategy_to_id("Diagonal Spread (Call)", -100) == "call_diagonal_spread"
    assert map_strategy_to_id("Diagonal Spread (Put)", -100) == "put_diagonal_spread"


def test_fallback_mapping():
    assert map_strategy_to_id("Unknown Strategy", 0) is None
    assert map_strategy_to_id("Stock", 1000) == "stock"
