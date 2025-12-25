"""
Variance Score Enrichment Strategy
"""

from typing import Any

from .base import EnrichmentStrategy


class ScoreEnrichmentStrategy(EnrichmentStrategy):
    """Calculates the composite Variance Score."""

    def enrich(self, candidate: dict[str, Any], ctx: Any) -> None:
        rules = ctx.config_bundle.get("trading_rules", {})

        # 1. BATS Efficiency Check
        price = candidate.get("price")
        vrp_s = candidate.get("vrp_structural")
        candidate["is_bats_efficient"] = bool(
            price
            and vrp_s is not None
            and rules["bats_efficiency_min_price"]
            <= float(price)
            <= rules["bats_efficiency_max_price"]
            and float(vrp_s) > rules["bats_efficiency_vrp_structural"]
        )

        # 2. Variance Score
        from variance.vol_screener import _calculate_variance_score

        candidate["Score"] = _calculate_variance_score(candidate, rules)

        proxy_haircut = float(rules.get("proxy_iv_score_haircut", 1.0))
        proxy_note = candidate.get("proxy") or candidate.get("Proxy")
        symbol = str(candidate.get("symbol", ""))
        source = candidate.get("data_source", "yfinance")

        # Only apply haircut if using a proxy AND we don't have institutional composite data
        if proxy_haircut < 1.0 and proxy_note and symbol.startswith("/") and source == "yfinance":
            try:
                candidate["Score"] = round(float(candidate.get("Score", 0.0)) * proxy_haircut, 1)
            except (TypeError, ValueError):
                pass
