from variance.models import Position
from variance.strategies.time_spread import TimeSpreadStrategy


def make_strategy():
    return TimeSpreadStrategy(
        "time_spread",
        {"management": {"profit_target_pct": 0.25}, "metadata": {}},
        {"profit_harvest_pct": 0.5},
    )


def _make_leg(call_put: str, quantity: str, strike: str) -> Position:
    return Position.from_row(
        {
            "Symbol": "AAPL",
            "Type": "Option",
            "Call/Put": call_put,
            "Quantity": quantity,
            "Strike Price": strike,
        }
    )


def test_is_tested_short_call_breached():
    strategy = make_strategy()
    legs = [_make_leg("Call", "-1", "100")]

    assert strategy.is_tested(legs, underlying_price=105.0) is True
    assert strategy.is_tested(legs, underlying_price=95.0) is False


def test_is_tested_short_put_breached():
    strategy = make_strategy()
    legs = [_make_leg("Put", "-1", "100")]

    assert strategy.is_tested(legs, underlying_price=95.0) is True
    assert strategy.is_tested(legs, underlying_price=105.0) is False


def test_is_tested_no_short_legs():
    strategy = make_strategy()
    legs = [_make_leg("Call", "1", "100")]

    assert strategy.is_tested(legs, underlying_price=105.0) is False


def test_check_harvest_uses_time_spread_target():
    strategy = make_strategy()
    action = strategy.check_harvest("MSFT", pl_pct=0.25, days_held=8)

    assert action is not None
    assert action.action_code == "HARVEST"
    assert "Time Spread Target" in action.logic
