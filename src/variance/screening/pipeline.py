"""
Screening Pipeline (Template Method)

Defines the skeleton of the volatility screening algorithm.
"""

import logging
import os
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Optional

import numpy as np

from variance.config_loader import ConfigBundle

from .benchmark import PipelineBenchmark
from .enrichment.base import EnrichmentStrategy

if TYPE_CHECKING:
    from variance.vol_screener import ScreenerConfig


@dataclass
class ScreeningContext:
    """Shared state passed through the screening pipeline."""

    config: "ScreenerConfig"
    config_bundle: ConfigBundle
    symbols: list[str] = field(default_factory=list)
    raw_data: dict[str, Any] = field(default_factory=dict)
    market_data_diagnostics: dict[str, int] = field(default_factory=dict)
    candidates: list[dict[str, Any]] = field(default_factory=list)
    counters: dict[str, int] = field(default_factory=dict)
    debug_rejections: dict[str, str] = field(default_factory=dict)
    portfolio_returns: Optional[np.ndarray] = None
    benchmark: Optional[PipelineBenchmark] = None


class ScreeningPipeline:
    """
    Template Method implementation for volatility screening.
    """

    def __init__(
        self,
        config: "ScreenerConfig",
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
        logger = logging.getLogger(__name__)

        # Enable benchmarking if VARIANCE_BENCHMARK env var is set
        enable_benchmark = os.getenv("VARIANCE_BENCHMARK", "").lower() in ("1", "true", "yes")
        if enable_benchmark:
            self.ctx.benchmark = PipelineBenchmark()
            self.ctx.benchmark.start()

        start_time = time.time()
        logger.info("Screening pipeline started")
        try:
            with self._measure("1. Load Symbols"):
                self._load_symbols()
            logger.info("Loaded %s symbols from watchlist", len(self.ctx.symbols))

            with self._measure("2. Fetch Market Data", len(self.ctx.symbols)):
                self._fetch_data()
            logger.info("Fetched market data for %s symbols", len(self.ctx.raw_data))

            with self._measure("3. Filter Candidates", len(self.ctx.raw_data)):
                self._filter_candidates()
            raw_count = len(self.ctx.raw_data)
            cand_count = len(self.ctx.candidates)
            pass_rate = (cand_count / raw_count * 100.0) if raw_count else 0.0
            logger.info(
                "Filtering complete: %s candidates from %s symbols",
                cand_count,
                raw_count,
                extra={"pass_rate": f"{pass_rate:.1f}%"},
            )

            with self._measure("4. Enrich Candidates", cand_count):
                self._enrich_candidates()
            logger.debug("Enrichment complete")

            with self._measure("5. Sort & Dedupe", cand_count):
                self._sort_and_dedupe()

            with self._measure("6. Build Report"):
                report = self._build_report()

            elapsed_ms = (time.time() - start_time) * 1000
            logger.info("Screening pipeline completed in %.0fms", elapsed_ms)

            if self.ctx.benchmark:
                self.ctx.benchmark.finish()
                self.ctx.benchmark.print_report()

            return report
        except Exception as exc:
            elapsed_ms = (time.time() - start_time) * 1000
            logger.error(
                "Screening pipeline failed after %.0fms: %s",
                elapsed_ms,
                exc,
                exc_info=True,
            )
            raise

    def _measure(self, name: str, items: int = 0) -> Any:
        """Helper to conditionally measure if benchmarking is enabled."""
        if self.ctx.benchmark:
            return self.ctx.benchmark.measure(name, items)
        else:
            from contextlib import nullcontext

            return nullcontext()

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

        rules = self.ctx.config_bundle.get("trading_rules", {})
        min_yield = float(rules.get("min_yield_percent", 0.0))
        include_option_quotes = min_yield > 0
        self.ctx.raw_data, self.ctx.market_data_diagnostics = fetch_market_data(
            self.ctx.symbols, include_option_quotes=include_option_quotes
        )

    def _filter_candidates(self) -> None:
        """Step 3: Apply specifications (Hook)."""
        from .steps.filter import apply_specifications

        debug_rejections: dict[str, str] = {}
        self.ctx.candidates, self.ctx.counters = apply_specifications(
            self.ctx.raw_data,
            self.ctx.config,
            self.ctx.config_bundle.get("trading_rules", {}),
            self.ctx.config_bundle.get("market_config", {}),
            portfolio_returns=self.ctx.portfolio_returns,
            rejections=debug_rejections,
        )
        if getattr(self.ctx.config, "debug", False):
            self.ctx.debug_rejections = debug_rejections

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
            self.ctx.market_data_diagnostics,
            self.ctx.debug_rejections,
        )

    def _build_enrichment_chain(self) -> list[EnrichmentStrategy]:
        """Compose the list of enrichment strategies."""
        from .enrichment.score import ScoreEnrichmentStrategy
        from .enrichment.vrp import VrpEnrichmentStrategy

        return [
            VrpEnrichmentStrategy(),
            ScoreEnrichmentStrategy(),
        ]
