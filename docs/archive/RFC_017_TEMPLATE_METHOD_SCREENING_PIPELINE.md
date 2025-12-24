# RFC 017: Template Method + Strategy Pattern for Screening Pipeline

| Status | IMPLEMENTED |
| :--- | :--- |
| **Author** | Variance (Quant Agent) |
| **Date** | 2025-12-23 |
| **Area** | Architecture / Complexity Reduction |
| **Complexity Targets** | `vol_screener.py::screen_volatility()` (351 lines), `strategy_detector.py::_cluster_same_open_date()` (165 lines) |

## 1. Problem Statement

### 1.1 `screen_volatility()` Analysis

The `screen_volatility()` function in `/Users/eric.johnson@verinext.com/Projects/variance-yfinance/src/variance/vol_screener.py` (lines 306-656) is a "God Function":

| Metric | Current Value | Target |
|--------|--------------|--------|
| Lines of Code | 351 | < 100 (orchestrator) |
| Cyclomatic Complexity | ~25 | < 10 |
| Responsibilities | 8+ | Single (orchestration) |

**Current Responsibilities (Interleaved):**
1. Load watchlist from CSV
2. Fetch market data (threaded)
3. Filter by exclusion lists
4. Apply Specification Pattern filters
5. Calculate compression ratio
6. Calculate VRP tactical
7. Determine signal/regime types
8. Calculate variance score
9. Build candidate data
10. Deduplicate by root
11. Sort by signal quality
12. Build summary report

### 1.2 `_cluster_same_open_date()` Analysis

The `_cluster_same_open_date()` function in `/Users/eric.johnson@verinext.com/Projects/variance-yfinance/src/variance/strategy_detector.py` (lines 596-760) exhibits:

| Metric | Current Value | Target |
|--------|--------------|--------|
| Lines of Code | 165 | < 50 (per step) |
| Nesting Depth | 4 levels | 2 levels |
| Responsibilities | 5 | 1 per method |

**Current Flow:**
1. Extract leg info (type, strike, quantity, side)
2. Sort legs
3. Take 4-leg named clusters (butterflies, condors)
4. Take 3-leg named clusters (lizards)
5. Pair verticals by strike proximity
6. Combine verticals into iron condors
7. Pair remaining shorts into strangles

## 2. Proposed Solution

### 2.1 Template Method Pattern (for `screen_volatility`)

The Template Method pattern defines the skeleton of an algorithm, deferring specific steps to subclasses or hook methods.

```
+---------------------------+
|    ScreeningPipeline      |
|---------------------------|
| + execute() : Report      |  <-- Template Method
| # load_symbols()          |  <-- Concrete
| # fetch_data()            |  <-- Concrete
| # filter_candidates()     |  <-- Hook (uses Specifications)
| # enrich_candidates()     |  <-- Hook (calculate scores)
| # sort_and_dedupe()       |  <-- Concrete
| # build_report()          |  <-- Concrete
+---------------------------+
```

### 2.2 Strategy Pattern (for Enrichment)

Different "Enrichment Strategies" can be plugged in for different use cases:

```
+-------------------------+       +--------------------------+
| EnrichmentStrategy      |       | VrpEnrichmentStrategy    |
|-------------------------|       |--------------------------|
| + enrich(candidate)     |<----->| + enrich(candidate)      |
+-------------------------+       | - calc_vrp_tactical()    |
        ^                         | - calc_compression()     |
        |                         | - determine_signal()     |
        |                         +--------------------------+
        |
+---------------------------+
| ScoreEnrichmentStrategy   |
|---------------------------|
| + enrich(candidate)       |
| - calc_variance_score()   |
+---------------------------+
```

### 2.3 Template Method (for `_cluster_same_open_date`)

```
+-----------------------------+
|   ClusteringPipeline        |
|-----------------------------|
| + cluster(legs) : clusters  |  <-- Template Method
| # extract_leg_info()        |  <-- Step 1
| # take_named_clusters(4)    |  <-- Step 2
| # take_named_clusters(3)    |  <-- Step 3
| # pair_verticals()          |  <-- Step 4
| # combine_into_condors()    |  <-- Step 5
| # pair_strangles()          |  <-- Step 6
+-----------------------------+
```

## 3. Technical Design

### 3.1 File Tree

```
src/variance/
├── screening/                       # NEW: Screening submodule
│   ├── __init__.py                  # Exports: ScreeningPipeline
│   ├── pipeline.py                  # ScreeningPipeline (Template Method)
│   ├── steps/                       # Pipeline steps
│   │   ├── __init__.py
│   │   ├── load.py                  # load_symbols()
│   │   ├── fetch.py                 # fetch_data()
│   │   ├── filter.py                # filter_candidates()
│   │   ├── enrich.py                # Enrichment strategy composition
│   │   ├── sort.py                  # sort_and_dedupe()
│   │   └── report.py                # build_report()
│   └── enrichment/                  # Enrichment strategies
│       ├── __init__.py
│       ├── base.py                  # EnrichmentStrategy ABC
│       ├── vrp.py                   # VrpEnrichmentStrategy
│       └── score.py                 # ScoreEnrichmentStrategy
├── clustering/                      # NEW: Clustering submodule
│   ├── __init__.py                  # Exports: ClusteringPipeline
│   ├── pipeline.py                  # ClusteringPipeline (Template Method)
│   └── steps/                       # Clustering steps
│       ├── __init__.py
│       ├── extract.py               # extract_leg_info()
│       ├── named.py                 # take_named_clusters()
│       ├── verticals.py             # pair_verticals()
│       ├── condors.py               # combine_into_condors()
│       └── strangles.py             # pair_strangles()
├── vol_screener.py                  # MODIFIED: Thin wrapper
├── strategy_detector.py             # MODIFIED: Uses ClusteringPipeline
```

### 3.2 Interface Specifications

#### A. `ScreeningPipeline` (Template Method)
```python
# Location: src/variance/screening/pipeline.py
from dataclasses import dataclass
from typing import Any, Optional
from .steps import load, fetch, filter, enrich, sort, report
from ..config_loader import ConfigBundle

@dataclass
class ScreeningContext:
    """Shared state passed through pipeline steps."""
    config: "ScreenerConfig"
    config_bundle: ConfigBundle
    symbols: list[str] = None
    raw_data: dict[str, dict] = None
    candidates: list[dict] = None
    counters: dict[str, int] = None

class ScreeningPipeline:
    """
    Template Method implementation for volatility screening.

    The execute() method defines the algorithm skeleton.
    Each step can be overridden in subclasses for customization.
    """

    def __init__(self, config: "ScreenerConfig", config_bundle: ConfigBundle):
        self.ctx = ScreeningContext(config=config, config_bundle=config_bundle)
        self._enrichment_strategies = self._build_enrichment_chain()

    def execute(self) -> dict[str, Any]:
        """
        Template Method: Defines the screening algorithm.

        Steps:
        1. Load symbols from watchlist
        2. Fetch market data (parallel)
        3. Filter using Specification pattern
        4. Enrich with VRP/Score calculations
        5. Sort and deduplicate
        6. Build final report
        """
        self._load_symbols()
        self._fetch_data()
        self._filter_candidates()
        self._enrich_candidates()
        self._sort_and_dedupe()
        return self._build_report()

    # --- Template Steps (can be overridden) ---

    def _load_symbols(self) -> None:
        """Step 1: Load symbols from watchlist."""
        self.ctx.symbols = load.load_watchlist(
            self.ctx.config_bundle.get("system_config", {})
        )
        if self.ctx.config.limit:
            self.ctx.symbols = self.ctx.symbols[:self.ctx.config.limit]

    def _fetch_data(self) -> None:
        """Step 2: Fetch market data in parallel."""
        self.ctx.raw_data = fetch.fetch_market_data(self.ctx.symbols)

    def _filter_candidates(self) -> None:
        """Step 3: Apply Specification filters."""
        self.ctx.candidates, self.ctx.counters = filter.apply_specifications(
            self.ctx.raw_data,
            self.ctx.config,
            self.ctx.config_bundle.get("trading_rules", {})
        )

    def _enrich_candidates(self) -> None:
        """Step 4: Enrich candidates with calculated metrics."""
        for strategy in self._enrichment_strategies:
            for candidate in self.ctx.candidates:
                strategy.enrich(candidate, self.ctx)

    def _sort_and_dedupe(self) -> None:
        """Step 5: Sort by quality and deduplicate by root."""
        self.ctx.candidates = sort.sort_and_dedupe(self.ctx.candidates)

    def _build_report(self) -> dict[str, Any]:
        """Step 6: Build final report structure."""
        return report.build_report(self.ctx.candidates, self.ctx.counters, self.ctx.config)

    def _build_enrichment_chain(self) -> list["EnrichmentStrategy"]:
        """Hook: Build the chain of enrichment strategies."""
        from .enrichment import VrpEnrichmentStrategy, ScoreEnrichmentStrategy
        return [
            VrpEnrichmentStrategy(),
            ScoreEnrichmentStrategy(),
        ]
```

#### B. `EnrichmentStrategy` (Strategy Pattern)
```python
# Location: src/variance/screening/enrichment/base.py
from abc import ABC, abstractmethod
from typing import Any

class EnrichmentStrategy(ABC):
    """Abstract base class for candidate enrichment strategies."""

    @abstractmethod
    def enrich(self, candidate: dict[str, Any], ctx: "ScreeningContext") -> None:
        """
        Enrich a candidate in-place with calculated metrics.

        Args:
            candidate: Mutable candidate dict
            ctx: Screening context with rules and config
        """
        pass
```

```python
# Location: src/variance/screening/enrichment/vrp.py
from .base import EnrichmentStrategy
from typing import Any

class VrpEnrichmentStrategy(EnrichmentStrategy):
    """Calculates VRP-related metrics."""

    def enrich(self, candidate: dict[str, Any], ctx: "ScreeningContext") -> None:
        rules = ctx.config_bundle.get("trading_rules", {})

        # Compression Ratio
        hv20 = candidate.get("HV20")
        hv252 = candidate.get("HV252")
        if hv20 and hv252 and hv252 > 0:
            candidate["Compression Ratio"] = hv20 / hv252
        else:
            candidate["Compression Ratio"] = 1.0

        # VRP Tactical Markup
        iv30 = candidate.get("IV30")
        if hv20 and iv30:
            hv_floor = max(hv20, rules.get("hv_floor_percent", 5.0))
            raw_markup = (iv30 - hv_floor) / hv_floor
            candidate["VRP_Tactical_Markup"] = max(-0.99, min(3.0, raw_markup))

        # Signal Type
        candidate["Signal"] = self._determine_signal(candidate, rules)
        candidate["Regime"] = self._determine_regime(candidate, rules)

    def _determine_signal(self, c: dict, rules: dict) -> str:
        # (Logic extracted from _determine_signal_type)
        pass

    def _determine_regime(self, c: dict, rules: dict) -> str:
        # (Logic extracted from _determine_regime_type)
        pass
```

#### C. `ClusteringPipeline` (Template Method)
```python
# Location: src/variance/clustering/pipeline.py
from typing import Any
from .steps import extract, named, verticals, condors, strangles

class ClusteringContext:
    """Shared state for clustering pipeline."""
    def __init__(self, legs_with_idx: list[tuple[int, dict]]):
        self.leg_infos: list[dict] = []
        self.clusters: list[list[dict]] = []
        self.used_indices: set[int] = set()
        self.raw_legs = legs_with_idx

class ClusteringPipeline:
    """
    Template Method for clustering option legs into strategies.

    Replaces the monolithic _cluster_same_open_date() function.
    """

    def cluster(self, legs_with_idx: list[tuple[int, dict]]) -> tuple[list[list[dict]], set[int]]:
        """
        Template Method: Defines the clustering algorithm.

        Steps:
        1. Extract and normalize leg info
        2. Take 4-leg named clusters (IC, Butterfly)
        3. Take 3-leg named clusters (Lizards)
        4. Pair remaining verticals
        5. Combine credit verticals into ICs
        6. Pair remaining shorts into strangles
        """
        ctx = ClusteringContext(legs_with_idx)

        self._extract_leg_info(ctx)
        self._take_named_clusters(ctx, size=4)
        self._take_named_clusters(ctx, size=3)
        self._pair_verticals(ctx)
        self._combine_into_condors(ctx)
        self._pair_strangles(ctx)

        return ctx.clusters, ctx.used_indices

    def _extract_leg_info(self, ctx: ClusteringContext) -> None:
        """Step 1: Normalize leg data."""
        ctx.leg_infos = extract.extract_leg_info(ctx.raw_legs)

    def _take_named_clusters(self, ctx: ClusteringContext, size: int) -> None:
        """Step 2/3: Greedily match N-leg named strategies."""
        new_clusters = named.take_named_clusters(ctx.leg_infos, ctx.used_indices, size)
        ctx.clusters.extend(new_clusters)

    def _pair_verticals(self, ctx: ClusteringContext) -> None:
        """Step 4: Pair shorts with longs by strike proximity."""
        ctx.call_verticals, ctx.put_verticals = verticals.pair_verticals(
            ctx.leg_infos, ctx.used_indices
        )

    def _combine_into_condors(self, ctx: ClusteringContext) -> None:
        """Step 5: Combine matching credit verticals."""
        ic_clusters = condors.combine_into_condors(
            ctx.call_verticals, ctx.put_verticals, ctx.used_indices
        )
        ctx.clusters.extend(ic_clusters)

    def _pair_strangles(self, ctx: ClusteringContext) -> None:
        """Step 6: Pair remaining short calls/puts."""
        strangle_clusters = strangles.pair_strangles(ctx.leg_infos, ctx.used_indices)
        ctx.clusters.extend(strangle_clusters)
```

### 3.3 Modified `screen_volatility()` (Thin Wrapper)

```python
# Location: src/variance/vol_screener.py (MODIFIED)

from .screening import ScreeningPipeline
from .config_loader import load_config_bundle

def screen_volatility(
    config: ScreenerConfig,
    *,
    config_bundle: Optional[ConfigBundle] = None,
    config_dir: Optional[str] = None,
    strict: Optional[bool] = None,
) -> dict[str, Any]:
    """
    Scan the watchlist for high-volatility trading opportunities.

    This function is now a thin wrapper around ScreeningPipeline.
    """
    if config_bundle is None:
        config_bundle = load_config_bundle(config_dir=config_dir, strict=strict)

    pipeline = ScreeningPipeline(config, config_bundle)
    return pipeline.execute()
```

### 3.4 Data Flow (Screening Pipeline)

```
ScreenerConfig + ConfigBundle
          |
          v
+-------------------------+
|  ScreeningPipeline      |
+-------------------------+
          |
          v
+-------------------------+
| 1. load_symbols()       |  --> symbols: list[str]
+-------------------------+
          |
          v
+-------------------------+
| 2. fetch_data()         |  --> raw_data: dict[sym, metrics]
+-------------------------+
          |
          v
+-------------------------+
| 3. filter_candidates()  |  --> candidates: list[dict], counters
|    (Specification Gate) |
+-------------------------+
          |
          v
+-------------------------+
| 4. enrich_candidates()  |
|    [VrpStrategy]        |  --> VRP Tactical, Signal, Regime
|    [ScoreStrategy]      |  --> Variance Score
+-------------------------+
          |
          v
+-------------------------+
| 5. sort_and_dedupe()    |  --> sorted, unique candidates
+-------------------------+
          |
          v
+-------------------------+
| 6. build_report()       |  --> {"candidates": [...], "summary": {...}}
+-------------------------+
```

## 4. Benefits & Trade-offs

### 4.1 Benefits

| Benefit | Description |
|---------|-------------|
| **Testability** | Each step/strategy testable in isolation |
| **Extensibility** | New enrichment strategies via composition |
| **Readability** | Pipeline structure is self-documenting |
| **Reusability** | Steps can be reused in other pipelines |
| **Debugging** | Can log/trace each pipeline step |

### 4.2 Trade-offs

| Trade-off | Mitigation |
|-----------|------------|
| More modules | Logical grouping in `screening/`, `clustering/` |
| State passing | `ScreeningContext` bundles all state |
| Slight indirection | Clear naming conventions |

## 5. Migration Strategy

### Phase 1: Screening Pipeline (2 days)
1. Create `src/variance/screening/` module
2. Extract steps from `screen_volatility()`
3. Implement enrichment strategies
4. Wire up pipeline

### Phase 2: Clustering Pipeline (1 day)
1. Create `src/variance/clustering/` module
2. Extract steps from `_cluster_same_open_date()`
3. Wire up pipeline

### Phase 3: Integration (1 day)
1. Update `vol_screener.py` to use pipeline
2. Update `strategy_detector.py` to use pipeline
3. Run regression tests

## 6. Testing Strategy

### 6.1 Unit Tests (Per Step)
```python
# tests/screening/test_vrp_enrichment.py
def test_vrp_enrichment_calculates_compression():
    candidate = {"HV20": 15.0, "HV252": 20.0, "IV30": 25.0}
    strategy = VrpEnrichmentStrategy()
    strategy.enrich(candidate, ctx)
    assert candidate["Compression Ratio"] == 0.75
```

### 6.2 Integration Tests
```python
# tests/screening/test_pipeline.py
def test_pipeline_produces_valid_report():
    config = ScreenerConfig(limit=10)
    pipeline = ScreeningPipeline(config, load_config_bundle())
    result = pipeline.execute()
    assert "candidates" in result
    assert "summary" in result
```

## 7. Status
**Proposed.** Ready for Developer implementation upon approval.
