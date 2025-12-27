from datetime import datetime

import pytz

from variance.market_data.clock import is_market_open


def _et(dt: datetime) -> datetime:
    tz = pytz.timezone("US/Eastern")
    return tz.localize(dt)


def test_market_open_weekday_during_hours():
    now = _et(datetime(2024, 6, 4, 10, 0))
    assert is_market_open(now) is True


def test_market_closed_weekend():
    now = _et(datetime(2024, 6, 8, 10, 0))  # Saturday
    assert is_market_open(now) is False


def test_market_closed_before_open_and_after_close():
    before_open = _et(datetime(2024, 6, 4, 9, 0))
    after_close = _et(datetime(2024, 6, 4, 16, 30))
    assert is_market_open(before_open) is False
    assert is_market_open(after_close) is False


def test_market_closed_holiday():
    now = _et(datetime(2024, 12, 25, 12, 0))
    assert is_market_open(now) is False


def test_market_closed_observed_holiday():
    now = _et(datetime(2026, 7, 3, 12, 0))  # Observed Friday
    holiday = _et(datetime(2026, 7, 4, 0, 0))  # Saturday holiday
    assert is_market_open(now, holiday_calendar=[holiday]) is False


def test_market_open_custom_holiday_calendar():
    now = _et(datetime(2024, 6, 4, 10, 0))
    holiday = _et(datetime(2024, 6, 4, 0, 0))
    assert is_market_open(now, holiday_calendar=[holiday]) is False


def test_market_open_with_naive_datetime():
    naive = datetime(2024, 6, 4, 10, 0)
    assert is_market_open(naive) is True
