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

        # 3. TUI Mapping
        candidate["Symbol"] = candidate.get("symbol")
        candidate["Price"] = candidate.get("price", 0.0)

        from variance.common import map_sector_to_asset_class

        candidate["Asset Class"] = map_sector_to_asset_class(
            str(candidate.get("sector", "Unknown"))
        )

        # 4. Held Status
        held_symbols = set(s.upper() for s in ctx.config.held_symbols)
        candidate["is_held"] = str(candidate.get("symbol", "")).upper() in held_symbols
