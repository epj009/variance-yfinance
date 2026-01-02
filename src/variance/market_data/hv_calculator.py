"""
Historical Volatility Calculator.

Calculates HV30 and HV90 from historical OHLC candle data using
the standard log returns methodology.

Formula:
HV = σ(log returns) × √252

Where:
- σ = standard deviation of log returns
- 252 = typical trading days per year (annualization factor)
- log returns = ln(Price[i] / Price[i-1])
"""

import logging
import math
import statistics
from typing import Optional

from variance.market_data.dxlink_client import CandleData

__all__ = ["CandleData", "calculate_hv_metrics", "calculate_hv30", "calculate_hv90"]

logger = logging.getLogger(__name__)


def calculate_hv_from_candles(candles: list[CandleData], window: int = 30) -> Optional[float]:
    """
    Calculate historical volatility from daily candles.

    Uses the standard log returns methodology:
    1. Extract closing prices
    2. Calculate log returns: ln(close[i] / close[i-1])
    3. Calculate standard deviation of returns
    4. Annualize: σ × √252

    Args:
        candles: List of CandleData objects (must be sorted chronologically)
        window: Rolling window in days (30 or 90 typical)

    Returns:
        Annualized historical volatility as decimal (e.g., 0.25 = 25%)
        None if insufficient data

    Example:
        >>> candles = get_daily_candles("AAPL", days=120)
        >>> hv30 = calculate_hv_from_candles(candles, window=30)
        >>> print(f"HV30: {hv30:.4f} ({hv30*100:.2f}%)")
        HV30: 0.2547 (25.47%)
    """
    # Need window + 1 candles (for window returns)
    required_candles = window + 1
    if len(candles) < required_candles:
        logger.warning(
            f"Insufficient candles for HV{window}: have {len(candles)}, need {required_candles}"
        )
        return None

    # Extract most recent closes
    recent_candles = candles[-required_candles:]
    closes = [c.close for c in recent_candles]

    # Validate prices
    if any(price <= 0 for price in closes):
        logger.error("Invalid price data: found non-positive prices")
        return None

    # Calculate log returns
    returns = []
    for i in range(1, len(closes)):
        try:
            log_return = math.log(closes[i] / closes[i - 1])
            returns.append(log_return)
        except (ValueError, ZeroDivisionError) as e:
            logger.error(f"Error calculating return at index {i}: {e}")
            return None

    # Verify we have enough returns
    if len(returns) < window:
        logger.warning(f"Insufficient returns for HV{window}: have {len(returns)}, need {window}")
        return None

    # Calculate standard deviation
    try:
        std_dev = statistics.stdev(returns)
    except statistics.StatisticsError as e:
        logger.error(f"Error calculating standard deviation: {e}")
        return None

    # Annualize (252 trading days per year)
    hv = std_dev * math.sqrt(252)

    logger.debug(f"HV{window} calculated: {hv:.4f} (std_dev={std_dev:.6f}, returns={len(returns)})")

    return hv


def calculate_hv30(candles: list[CandleData]) -> Optional[float]:
    """
    Calculate 30-day historical volatility.

    Convenience wrapper for calculate_hv_from_candles with window=30.

    Args:
        candles: List of daily CandleData objects

    Returns:
        Annualized HV30 as decimal, or None if insufficient data
    """
    return calculate_hv_from_candles(candles, window=30)


def calculate_hv90(candles: list[CandleData]) -> Optional[float]:
    """
    Calculate 90-day historical volatility.

    Convenience wrapper for calculate_hv_from_candles with window=90.

    Args:
        candles: List of daily CandleData objects

    Returns:
        Annualized HV90 as decimal, or None if insufficient data
    """
    return calculate_hv_from_candles(candles, window=90)


def calculate_hv_metrics(
    candles: list[CandleData],
) -> dict[str, Optional[float]]:
    """
    Calculate both HV30 and HV90 from candles.

    Args:
        candles: List of daily CandleData objects

    Returns:
        Dictionary with keys 'hv30' and 'hv90'
        Values are None if insufficient data for that metric
    """
    hv30 = calculate_hv30(candles)
    hv90 = calculate_hv90(candles)

    if hv30 is not None:
        logger.debug(f"HV30: {hv30:.4f} ({hv30 * 100:.2f}%)")
    else:
        logger.warning("Could not calculate HV30")

    if hv90 is not None:
        logger.debug(f"HV90: {hv90:.4f} ({hv90 * 100:.2f}%)")
    else:
        logger.warning("Could not calculate HV90")

    return {"hv30": hv30, "hv90": hv90}
