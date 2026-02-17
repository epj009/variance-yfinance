"""
Variance Score Enrichment Strategy
"""

from typing import Any

from .base import EnrichmentStrategy


class ScoreEnrichmentStrategy(EnrichmentStrategy):
    """Calculates the composite Variance Score."""

    def enrich(self, candidate: dict[str, Any], ctx: Any) -> None:
        rules = ctx.config_bundle.get("trading_rules", {})

        # 1. Variance Score
        from variance.scoring import calculate_variance_score

        candidate["score"] = calculate_variance_score(candidate, rules, ctx.config)

        proxy_haircut_raw = rules.get("proxy_iv_score_haircut", 1.0)
        proxy_haircut = float(proxy_haircut_raw) if proxy_haircut_raw is not None else 1.0

        proxy_note = candidate.get("proxy") or candidate.get("Proxy")
        symbol = str(candidate.get("symbol", ""))
        # Only apply haircut if using a proxy AND we don't have institutional composite data
        if proxy_haircut < 1.0 and proxy_note and symbol.startswith("/"):
            try:
                score_raw = candidate.get("score", 0.0)
                score = float(score_raw) if score_raw is not None else 0.0
                candidate["score"] = round(score * proxy_haircut, 1)
            except (TypeError, ValueError):
                pass
