"""
VRP Enrichment Strategy
"""

from typing import Any

from .base import EnrichmentStrategy


class VrpEnrichmentStrategy(EnrichmentStrategy):
    """Calculates VRP-related metrics and regime types."""

    def enrich(self, candidate: dict[str, Any], ctx: Any) -> None:
        rules = ctx.config_bundle.get("trading_rules", {})

        # 1. Basic Stats (Prefer Tastytrade HV fields, fallback to yfinance)
        hv30 = candidate.get("hv30") or candidate.get("hv20")  # TT first, yf fallback
        hv90 = candidate.get("hv90") or candidate.get("hv252")  # TT first, yf fallback
        hv20 = candidate.get("hv20")  # Keep for coiled_medium calculation
        iv30 = candidate.get("iv")
        hv_floor_abs = float(rules.get("hv_floor_percent", 5.0))

        # 2. Compression (Use HV30/HV90, fallback to HV20/HV252)
        candidate["Compression Ratio"] = 1.0
        if hv30 and hv90 and hv90 > 0:
            candidate["Compression Ratio"] = float(hv30) / float(hv90)

        # 3. Tactical Markup (Use HV30, fallback to HV20)
        candidate["vrp_tactical_markup"] = None
        if hv30 is not None and iv30 is not None and float(hv30) > 0:
            hv_f = max(float(hv30), hv_floor_abs)
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
