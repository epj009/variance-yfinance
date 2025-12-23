"""
Short Theta Strategy Class

Handles logic for strategies that are net sellers of premium (Strangles, Iron Condors, Lizards).
"""

from typing import Any, Optional

from ..portfolio_parser import is_stock_type, parse_currency
from .base import BaseStrategy


class ShortThetaStrategy(BaseStrategy):
    """
    Base for all strategies where edge is derived from time decay (Theta).
    Includes mechanical 'Tested' checks and institutional Toxic Theta filters.
    """

    def is_tested(self, legs: list[dict[str, Any]], underlying_price: float) -> bool:
        """Standard check: Is any short leg In-The-Money?"""
        for leg in legs:
            if is_stock_type(leg.get("Type", "")):
                continue

            qty = parse_currency(leg.get("Quantity", "0"))
            if qty >= 0:
                continue  # Only short legs can be "tested" in this context

            otype = leg.get("Call/Put")
            strike = parse_currency(leg.get("Strike Price", "0"))

            if otype == "Call" and underlying_price > strike:
                return True
            if otype == "Put" and underlying_price < strike:
                return True

        return False

    def check_toxic_theta(
        self, metrics: dict[str, Any], market_data: dict[str, Any]
    ) -> tuple[Optional[str], str]:
        """
        Calculates if the Theta 'Carry' is sufficient to cover the Gamma 'Cost'.
        Institutional standard for stop-losses on premium sellers.
        """
        cluster_theta_raw = metrics.get("cluster_theta_raw", 0.0)
        cluster_gamma_raw = metrics.get("cluster_gamma_raw", 0.0)

        # We only care if we are net short theta (collecting premium)
        if cluster_theta_raw <= 0:
            return None, ""

        root = metrics.get("root")
        m_data = market_data.get(root, {})
        hv_ref = m_data.get("hv20") or m_data.get("hv252")
        price = metrics.get("price") or 0.0

        if not hv_ref or price <= 0:
            return None, ""

        hv_floor = self.rules.get("hv_floor_percent", 5.0)
        hv_ref_floored = max(hv_ref, hv_floor)

        # 1SD move in points = Price * (HV / sqrt(252))
        # Institution uses 15.87 as constant for sqrt(252)
        em_1sd = price * (hv_ref_floored / 100.0 / 15.87)

        # Gamma Cost = 0.5 * Gamma * (Move^2)
        expected_gamma_cost = 0.5 * abs(cluster_gamma_raw) * (em_1sd**2)

        if expected_gamma_cost > 0:
            efficiency = abs(cluster_theta_raw) / expected_gamma_cost
            threshold = self.rules.get("theta_efficiency_low", 0.10)

            if efficiency < threshold:
                return "TOXIC", f"Toxic Theta: Carry/Cost {efficiency:.2f}x < {threshold:.2f}x"

        return None, ""
