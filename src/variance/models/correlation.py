"""
Correlation Engine

Calculates rolling correlation matrices and portfolio-relative correlation
to detect macro concentration risks.
"""

import logging
from typing import cast

import numpy as np
from numpy.typing import NDArray

logger = logging.getLogger(__name__)


class CorrelationEngine:
    """Mathematical engine for calculating asset correlations."""

    @staticmethod
    def calculate_log_returns(prices: list[float]) -> NDArray[np.float64]:
        """Converts a price series into log returns."""
        if len(prices) < 2:
            return cast(NDArray[np.float64], np.asarray([], dtype=float))

        arr = cast(NDArray[np.float64], np.asarray(prices, dtype=float))
        # ln(P_t / P_t-1)
        returns = np.log(arr[1:] / arr[:-1])
        return returns

    @staticmethod
    def calculate_correlation(
        returns_a: NDArray[np.float64], returns_b: NDArray[np.float64]
    ) -> float:
        """Calculates Pearson Correlation Coefficient between two return series."""
        if len(returns_a) == 0 or len(returns_b) == 0:
            return 0.0

        # Ensure identical lengths by taking the minimum
        min_len = min(len(returns_a), len(returns_b))
        if min_len < 5:  # Require at least 5 points for any meaningful signal
            return 0.0

        a = returns_a[-min_len:]
        b = returns_b[-min_len:]

        # Validate input data quality
        if np.any(np.isnan(a)) or np.any(np.isnan(b)):
            logger.warning("NaN detected in returns for correlation calculation")
            return 0.0
        if np.any(np.isinf(a)) or np.any(np.isinf(b)):
            logger.warning("Inf detected in returns for correlation calculation")
            return 0.0

        correlation_matrix = np.corrcoef(a, b)
        corr_value = correlation_matrix[0, 1]

        # Validate output
        if np.isnan(corr_value) or np.isinf(corr_value):
            logger.warning("Invalid correlation result (NaN/Inf)")
            return 0.0

        return float(corr_value)

    @staticmethod
    def get_portfolio_proxy_returns(
        portfolio_returns: list[NDArray[np.float64]],
    ) -> NDArray[np.float64]:
        """
        Creates a synthetic 'Portfolio Return' series by averaging returns
        across all held positions.
        """
        if not portfolio_returns:
            return cast(NDArray[np.float64], np.asarray([], dtype=float))

        # Find minimum length to align series
        min_len = min(len(r) for r in portfolio_returns)
        aligned = [r[-min_len:] for r in portfolio_returns]

        # Simple average (could be weighted by BPR in future)
        proxy = np.mean(aligned, axis=0)
        return cast(NDArray[np.float64], np.asarray(proxy, dtype=float))
