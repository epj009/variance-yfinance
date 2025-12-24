"""
Correlation Engine

Calculates rolling correlation matrices and portfolio-relative correlation
to detect macro concentration risks.
"""

from typing import List

import numpy as np


class CorrelationEngine:
    """Mathematical engine for calculating asset correlations."""

    @staticmethod
    def calculate_log_returns(prices: List[float]) -> np.ndarray:
        """Converts a price series into log returns."""
        if len(prices) < 2:
            return np.array([])

        arr = np.array(prices)
        # ln(P_t / P_t-1)
        returns = np.log(arr[1:] / arr[:-1])
        return returns

    @staticmethod
    def calculate_correlation(returns_a: np.ndarray, returns_b: np.ndarray) -> float:
        """Calculates Pearson Correlation Coefficient between two return series."""
        if len(returns_a) == 0 or len(returns_b) == 0:
            return 0.0

        # Ensure identical lengths by taking the minimum
        min_len = min(len(returns_a), len(returns_b))
        if min_len < 5:  # Require at least 5 points for any meaningful signal
            return 0.0

        a = returns_a[-min_len:]
        b = returns_b[-min_len:]

        correlation_matrix = np.corrcoef(a, b)
        return float(correlation_matrix[0, 1])

    @staticmethod
    def get_portfolio_proxy_returns(portfolio_returns: List[np.ndarray]) -> np.ndarray:
        """
        Creates a synthetic 'Portfolio Return' series by averaging returns 
        across all held positions.
        """
        if not portfolio_returns:
            return np.array([])

        # Find minimum length to align series
        min_len = min(len(r) for r in portfolio_returns)
        aligned = [r[-min_len:] for r in portfolio_returns]

        # Simple average (could be weighted by BPR in future)
        proxy = np.mean(aligned, axis=0)
        return proxy
