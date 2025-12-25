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
        try:
            if hv30 is not None and hv90 is not None:
                hv90_f = float(hv90)
                if hv90_f > 0:
                    candidate["Compression Ratio"] = float(hv30) / hv90_f
        except (ValueError, TypeError):
            pass

        # 3. Tactical Markup (Use HV30, fallback to HV20)
        candidate["vrp_tactical_markup"] = None
        try:
            if hv30 is not None and iv30 is not None:
                hv30_f = float(hv30)
                if hv30_f > 0:
                    hv_f = max(hv30_f, hv_floor_abs)
                    raw_markup = (float(iv30) - hv_f) / hv_f
                    # Remove upper cap, maintain floor to prevent negative infinity
                    candidate["vrp_tactical_markup"] = max(-0.99, raw_markup)
        except (ValueError, TypeError):
            pass

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

        vrp_s_f = float(vrp_structural) if vrp_structural is not None else None
        hv20_f = float(hv20) if hv20 is not None else None
        hv60_f = float(candidate.get("hv60", 0)) or None

        flags = _create_candidate_flags(
            vrp_s_f,
            days_to_earn,
            candidate["Compression Ratio"],
            candidate["vrp_tactical_markup"],
            hv20_f,
            hv60_f,
            rules,
        )

        # Restore TUI keys
        iv_pct_val = candidate.get("iv_percentile")
        candidate["Signal"] = _determine_signal_type(
            flags, candidate["vrp_tactical_markup"], rules, iv_pct_val
        )
        candidate["Regime"] = _determine_regime_type(flags)
        candidate["Environment"] = _get_recommended_environment(candidate["Signal"])
        candidate["Earnings In"] = days_to_earn
        candidate["VRP Structural"] = vrp_structural
        candidate.update(flags)
