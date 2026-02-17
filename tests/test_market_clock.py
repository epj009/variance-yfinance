from datetime import datetime

import pytz

from variance.market_data.clock import (
    get_eastern_now,
    get_eastern_timestamp,
    is_market_open,
)


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


def test_get_eastern_now_has_timezone():
    """Test that get_eastern_now() returns a timezone-aware datetime."""
    now = get_eastern_now()
    assert now.tzinfo is not None, "get_eastern_now() should return timezone-aware datetime"
    assert str(now.tzinfo) == "US/Eastern", "Timezone should be US/Eastern"


def test_get_eastern_timestamp_format():
    """Test that get_eastern_timestamp() returns ISO 8601 with timezone offset."""
    timestamp = get_eastern_timestamp()
    # Verify it's a valid ISO format with timezone offset
    # Format: 2026-02-17T14:30:00-05:00 or 2026-02-17T14:30:00-04:00 (DST)
    assert isinstance(timestamp, str), "Timestamp should be a string"
    assert "T" in timestamp, "Timestamp should be ISO 8601 format with 'T' separator"
    # Verify timezone offset is present (either -05:00 or -04:00 depending on DST)
    assert "-05:00" in timestamp or "-04:00" in timestamp, (
        "Timestamp should have Eastern timezone offset"
    )
    # Verify it can be parsed back to datetime
    parsed = datetime.fromisoformat(timestamp)
    assert parsed.tzinfo is not None, "Parsed timestamp should preserve timezone info"


def test_is_market_open_with_eastern_timestamp():
    """Test that is_market_open() works with get_eastern_now() output."""
    # Get timezone-aware datetime from get_eastern_now
    eastern_now = get_eastern_now()
    # This should not raise an error
    result = is_market_open(eastern_now)
    assert isinstance(result, bool), "is_market_open should return a boolean"
