from datetime import datetime, timedelta, tzinfo
from datetime import time as pytime
from typing import Optional

import pytz


def _build_holidays(year: int, tz: tzinfo) -> list[datetime]:
    # Fixed date holidays
    holidays = [
        datetime(year, 1, 1, tzinfo=tz),  # New Year's Day
        datetime(year, 6, 19, tzinfo=tz),  # Juneteenth (observed since 2021)
        datetime(year, 7, 4, tzinfo=tz),  # Independence Day
        datetime(year, 12, 25, tzinfo=tz),  # Christmas
    ]

    def nth_weekday(year: int, month: int, weekday: int, n: int) -> datetime:
        """Find nth occurrence of weekday in month (0=Mon, 6=Sun)."""
        first_day = datetime(year, month, 1, tzinfo=tz)
        first_weekday = (weekday - first_day.weekday()) % 7
        return first_day + timedelta(days=first_weekday + (n - 1) * 7)

    holidays.append(nth_weekday(year, 1, 0, 3))  # MLK Day
    holidays.append(nth_weekday(year, 2, 0, 3))  # Presidents Day

    last_monday_may = nth_weekday(year, 5, 0, 5)
    if last_monday_may.month != 5:
        last_monday_may = nth_weekday(year, 5, 0, 4)
    holidays.append(last_monday_may)  # Memorial Day

    holidays.append(nth_weekday(year, 9, 0, 1))  # Labor Day
    holidays.append(nth_weekday(year, 11, 3, 4))  # Thanksgiving

    return holidays


def is_market_open(
    now: Optional[datetime] = None,
    *,
    tz_name: str = "US/Eastern",
    holiday_calendar: Optional[list[datetime]] = None,
) -> bool:
    """
    Checks if the NYSE is currently open.

    Accounts for:
    - Weekends (Sat/Sun)
    - Standard trading hours (9:30 AM - 4:00 PM ET)
    - Major US market holidays
    """
    tz = pytz.timezone(tz_name)
    current = now if now is not None else datetime.now(tz)
    if current.tzinfo is None:
        current = tz.localize(current)

    if current.weekday() >= 5:
        return False

    holidays = (
        holiday_calendar if holiday_calendar is not None else _build_holidays(current.year, tz)
    )

    for holiday in holidays:
        if current.date() == holiday.date():
            return False
        if holiday.weekday() == 6 and current.date() == (holiday + timedelta(days=1)).date():
            return False
        if holiday.weekday() == 5 and current.date() == (holiday - timedelta(days=1)).date():
            return False

    return pytime(9, 30) <= current.time() <= pytime(16, 0)


__all__ = ["is_market_open"]
