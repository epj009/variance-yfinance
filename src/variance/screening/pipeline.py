"""
Screening Pipeline (Template Method)

Defines the skeleton of the volatility screening algorithm.
"""

from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np

from variance.config_loader import ConfigBundle

from .enrichment.base import EnrichmentStrategy


@dataclass
class ScreeningContext:
    """Shared state passed through the screening pipeline."""

    config: Any  # ScreenerConfig
    config_bundle: ConfigBundle
    symbols: list[str] = field(default_factory=list)
    raw_data: dict[str, Any] = field(default_factory=dict)
    candidates: list[dict[str, Any]] = field(default_factory=list)
    counters: dict[str, int] = field(default_factory=dict)
    portfolio_returns: Optional[np.ndarray] = None


class ScreeningPipeline:
    """
    Template Method implementation for volatility screening.
    """

    def __init__(
        self,
        config: Any,
        config_bundle: ConfigBundle,
        portfolio_returns: Optional[np.ndarray] = None,
    ):
        self.ctx = ScreeningContext(
            config=config, config_bundle=config_bundle, portfolio_returns=portfolio_returns
        )
        self._enrichment_strategies: list[EnrichmentStrategy] = self._build_enrichment_chain()

    def execute(self) -> dict[str, Any]:
        """
        The Template Method: Defines the fixed execution order.
        """
        self._load_symbols()
        self._fetch_data()
        self._filter_candidates()
        self._enrich_candidates()
        self._sort_and_dedupe()
        return self._build_report()

    def _load_symbols(self) -> None:
        """Step 1: Load from watchlist (Hook)."""
        from .steps.load import load_watchlist

        system_config = self.ctx.config_bundle.get("system_config", {})
        self.ctx.symbols = load_watchlist(system_config)
        if self.ctx.config.limit:
            self.ctx.symbols = self.ctx.symbols[: self.ctx.config.limit]

    def _fetch_data(self) -> None:
        """Step 2: Fetch market data (Hook)."""
        from .steps.fetch import fetch_market_data

        self.ctx.raw_data = fetch_market_data(self.ctx.symbols)

    def _filter_candidates(self) -> None:
        """Step 3: Apply specifications (Hook)."""
        from .steps.filter import apply_specifications

        self.ctx.candidates, self.ctx.counters = apply_specifications(
            self.ctx.raw_data,
            self.ctx.config,
            self.ctx.config_bundle.get("trading_rules", {}),
            self.ctx.config_bundle.get("market_config", {}),
            portfolio_returns=self.ctx.portfolio_returns,
        )

    def _enrich_candidates(self) -> None:
        """Step 4: Execute enrichment strategies (Hook)."""
        for strategy in self._enrichment_strategies:
            for candidate in self.ctx.candidates:
                strategy.enrich(candidate, self.ctx)

    def _sort_and_dedupe(self) -> None:
        """Step 5: Clean the candidate list (Hook)."""
        from .steps.sort import sort_and_dedupe

        self.ctx.candidates = sort_and_dedupe(self.ctx.candidates)

    def _build_report(self) -> dict[str, Any]:
        """Step 6: Construct final JSON report (Hook)."""
        from .steps.report import build_report

        return build_report(
            self.ctx.candidates,
            self.ctx.counters,
            self.ctx.config,
            self.ctx.config_bundle.get("trading_rules", {}),
        )

    def _build_enrichment_chain(self) -> list[EnrichmentStrategy]:
        """Compose the list of enrichment strategies."""
        from .enrichment.score import ScoreEnrichmentStrategy
        from .enrichment.vrp import VrpEnrichmentStrategy

        return [
            VrpEnrichmentStrategy(),
            ScoreEnrichmentStrategy(),
        ]
