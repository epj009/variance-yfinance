from variance.models import Position
from variance.strategies.butterfly import ButterflyStrategy


def make_strategy():
    return ButterflyStrategy(
        "butterfly",
        {"management": {"profit_target_pct": 0.25}, "metadata": {}},
        {"profit_harvest_pct": 0.5},
    )


def _make_leg(quantity: str, strike: str) -> Position:
    return Position.from_row(
        {
            "Symbol": "AAPL",
            "Type": "Option",
            "Quantity": quantity,
            "Strike Price": strike,
        }
    )


def test_is_tested_outside_short_strikes():
    strategy = make_strategy()
    legs = [
        _make_leg("-1", "100"),
        _make_leg("-1", "110"),
        _make_leg("1", "90"),
    ]

    assert strategy.is_tested(legs, underlying_price=120.0) is True
    assert strategy.is_tested(legs, underlying_price=105.0) is False


def test_is_tested_no_short_strikes():
    strategy = make_strategy()
    legs = [
        _make_leg("1", "100"),
        _make_leg("1", "110"),
    ]

    assert strategy.is_tested(legs, underlying_price=120.0) is False


def test_check_harvest_uses_pin_target():
    strategy = make_strategy()
    action = strategy.check_harvest("AAPL", pl_pct=0.25, days_held=10)

    assert action is not None
    assert action.action_code == "HARVEST"
    assert "Pin Target Hit" in action.logic
