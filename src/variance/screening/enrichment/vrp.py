"""
VRP Enrichment Strategy
"""

from typing import Any

from .base import EnrichmentStrategy


class VrpEnrichmentStrategy(EnrichmentStrategy):
    """Calculates VRP-related metrics and regime types."""

    def enrich(self, candidate: dict[str, Any], ctx: Any) -> None:
        rules = ctx.config_bundle.get("trading_rules", {})

        # 1. Basic Stats (Use legacy keys for TUI compat)
        hv20 = candidate.get("hv20")
        hv252 = candidate.get("hv252")
        iv30 = candidate.get("iv")
        hv_floor_abs = float(rules.get("hv_floor_percent", 5.0))

        # 2. Compression
        candidate["Compression Ratio"] = 1.0
        if hv20 and hv252 and hv252 > 0:
            candidate["Compression Ratio"] = float(hv20) / float(hv252)

        # 3. Tactical Markup
        candidate["vrp_tactical_markup"] = None
        if hv20 is not None and iv30 is not None and float(hv20) > 0:
            hv_f = max(float(hv20), hv_floor_abs)
            raw_markup = (float(iv30) - hv_f) / hv_f
            candidate["vrp_tactical_markup"] = max(-0.99, min(3.0, raw_markup))

        # 4. Signal Synthesis
        from variance.vol_screener import (
            _create_candidate_flags,
            _determine_regime_type,
            _determine_signal_type,
            _get_recommended_environment,
            get_days_to_date,
        )

        days_to_earn = get_days_to_date(candidate.get("earnings_date"))
        vrp_structural = candidate.get("vrp_structural")

        flags = _create_candidate_flags(
            float(vrp_structural) if vrp_structural is not None else None,
            days_to_earn,
            candidate["Compression Ratio"],
            candidate["vrp_tactical_markup"],
            float(hv20) if hv20 is not None else None,
            float(candidate.get("hv60", 0)) or None,
            rules,
        )

        # Restore TUI keys
        candidate["Signal"] = _determine_signal_type(flags, candidate["vrp_tactical_markup"], rules)
        candidate["Regime"] = _determine_regime_type(flags)
        candidate["Environment"] = _get_recommended_environment(candidate["Signal"])
        candidate["Earnings In"] = days_to_earn
        candidate["VRP Structural"] = vrp_structural
        candidate.update(flags)
