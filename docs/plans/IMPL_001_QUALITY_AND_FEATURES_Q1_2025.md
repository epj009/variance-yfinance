# IMPL-001: Quality Gates & Feature Development Q1 2025

| Document Type | Implementation Plan |
| :--- | :--- |
| **Status** | Ready for Contractor |
| **Owner** | TBD (Contractor) |
| **Estimated Effort** | 6-7 weeks (160-175 hours) |
| **Priority** | HIGH |
| **Start Date** | TBD |
| **Target Completion** | 6-7 weeks from start |

---

## Executive Summary

This implementation plan covers 5 phases of work to improve code quality, test coverage, documentation, and user-facing features for the Variance trading analysis platform. All work builds on the existing OOP architecture (RFC_016, RFC_017, RFC_018 already implemented).

**Deliverables:**
1. Strict type safety (mypy --strict passing)
2. 80%+ test coverage on core modules
3. Developer onboarding documentation
4. Multi-tag TUI rendering (user-facing feature)
5. Performance profiling and optimization (if needed)

**Dependencies:**
- Python 3.10+
- Existing codebase with RFCs 016-018 implemented
- Access to `src/variance/` module structure

---

## Prerequisites

### Required Knowledge
- ✅ Python 3.10+ (type hints, dataclasses, pattern matching)
- ✅ pytest testing framework
- ✅ mypy static type checking
- ✅ Object-oriented design patterns (Chain of Responsibility, Template Method)
- ✅ Terminal UI libraries (rich/textual) - for Phase 4

### Codebase Familiarity
Before starting, contractor should read:
- `docs/archive/RFC_016_CHAIN_OF_RESPONSIBILITY_TRIAGE.md`
- `docs/archive/RFC_017_TEMPLATE_METHOD_SCREENING_PIPELINE.md`
- `docs/archive/RFC_018_REGISTRY_PATTERN_STRATEGY_DETECTION.md`
- `README.md` (project overview)

### Environment Setup
```bash
# Clone repo
git clone <repo-url>
cd variance-yfinance

# Create virtual environment
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows

# Install dependencies
pip install -e ".[dev]"

# Verify setup
pytest tests/
ruff check .
mypy src/variance
```

---

## Phase 1: Strict Type Safety (Week 1)

### Objective
Enable and enforce strict type checking with mypy to prevent runtime type errors.

### Tasks

#### 1.1 Configure mypy strict mode

**File:** `pyproject.toml` (or create `mypy.ini`)

**Add configuration:**
```toml
[tool.mypy]
python_version = "3.10"
strict = true
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = true
disallow_any_generics = true
disallow_untyped_calls = true
disallow_incomplete_defs = true
check_untyped_defs = true
no_implicit_optional = true

# Allow gradual typing for some modules initially
[[tool.mypy.overrides]]
module = "tests.*"
disallow_untyped_defs = false
```

**Deliverable:** mypy configuration file committed to repo

**Acceptance Criteria:**
- ✅ Configuration file exists
- ✅ `mypy --strict src/variance` runs (may have errors)

**Estimated Effort:** 0.5 hours

---

#### 1.2 Catalog existing type errors

**Run mypy and document errors:**
```bash
mypy --strict src/variance > docs/type_errors_baseline.txt 2>&1
```

**Analyze errors and categorize:**
- Count errors by module
- Identify common patterns (missing return types, `Any` usage, etc.)
- Prioritize by module importance

**Deliverable:** `docs/type_errors_baseline.txt` with categorization

**Acceptance Criteria:**
- ✅ Baseline error count documented
- ✅ Errors categorized by module and type
- ✅ Priority order established

**Estimated Effort:** 1 hour

---

#### 1.3 Fix type errors in `models/`

**Files to fix:**
- `src/variance/models/position.py`
- `src/variance/models/portfolio.py`
- `src/variance/models/cluster.py`
- `src/variance/models/actions.py`
- `src/variance/models/specs.py`

**Common fixes:**

```python
# BEFORE: Missing return type
def get_root_symbol(self):
    return self.symbol.split()[0]

# AFTER: Explicit return type
def get_root_symbol(self) -> str:
    return self.symbol.split()[0]

# BEFORE: Untyped dict
def to_dict(self) -> dict:
    return {"symbol": self.symbol}

# AFTER: TypedDict or explicit annotation
from typing import TypedDict

class PositionDict(TypedDict):
    symbol: str
    quantity: float
    strike: Optional[float]

def to_dict(self) -> PositionDict:
    return {"symbol": self.symbol, "quantity": self.quantity, "strike": self.strike}

# BEFORE: Any in function signature
def process(data: Any) -> Any:
    ...

# AFTER: Specific types
def process(data: dict[str, float]) -> list[Position]:
    ...
```

**Deliverable:** All models/ files pass mypy strict

**Acceptance Criteria:**
- ✅ `mypy --strict src/variance/models/` produces zero errors
- ✅ All function signatures have type annotations
- ✅ No usage of `Any` type (except in very specific cases with `# type: ignore` comment)

**Estimated Effort:** 4 hours

---

#### 1.4 Fix type errors in `triage/`

**Files to fix:**
- `src/variance/triage/handler.py` (ABC)
- `src/variance/triage/request.py` (TriageRequest, TriageTag)
- `src/variance/triage/chain.py` (TriageChain)
- `src/variance/triage/handlers/*.py` (9 handler files)

**Key areas:**
- Handler `handle()` method signatures
- TriageRequest field types
- TriageTag field types
- Chain orchestration types

**Example:**
```python
# BEFORE
class TriageHandler(ABC):
    def handle(self, request):
        pass

# AFTER
from typing import TypeVar
from .request import TriageRequest

class TriageHandler(ABC):
    def __init__(self, rules: dict[str, Any]) -> None:
        self.rules = rules
        self._next: Optional["TriageHandler"] = None

    @abstractmethod
    def handle(self, request: TriageRequest) -> TriageRequest:
        pass

    def set_next(self, handler: "TriageHandler") -> "TriageHandler":
        self._next = handler
        return handler
```

**Deliverable:** All triage/ files pass mypy strict

**Acceptance Criteria:**
- ✅ `mypy --strict src/variance/triage/` produces zero errors
- ✅ All handler classes properly typed
- ✅ TriageRequest and TriageTag fully annotated

**Estimated Effort:** 6 hours

---

#### 1.5 Fix type errors in `classification/`

**Files to fix:**
- `src/variance/classification/base.py` (ABC + ClassificationContext)
- `src/variance/classification/registry.py` (ClassifierChain)
- `src/variance/classification/mapping.py` (strategy ID mapping)
- `src/variance/classification/classifiers/*.py` (10 classifier files)

**Similar patterns to triage/ fixes**

**Deliverable:** All classification/ files pass mypy strict

**Acceptance Criteria:**
- ✅ `mypy --strict src/variance/classification/` produces zero errors
- ✅ ClassificationContext fully typed
- ✅ All classifier classes properly typed

**Estimated Effort:** 6 hours

---

#### 1.6 Fix remaining type errors

**Modules:**
- `src/variance/screening/`
- `src/variance/clustering/`
- `src/variance/strategies/`
- Utility modules (config_loader, portfolio_parser, etc.)

**Deliverable:** Entire codebase passes mypy strict

**Acceptance Criteria:**
- ✅ `mypy --strict src/variance/` produces zero errors
- ✅ CI/CD pipeline configured to run mypy on every commit
- ✅ Documentation updated with type checking instructions

**Estimated Effort:** 8 hours

---

#### 1.7 Add mypy to CI/CD

**File:** `.github/workflows/ci.yml` (or equivalent)

**Add step:**
```yaml
- name: Type checking with mypy
  run: |
    pip install mypy
    mypy --strict src/variance
```

**Deliverable:** CI fails if type errors introduced

**Acceptance Criteria:**
- ✅ CI runs mypy --strict
- ✅ Builds fail on type errors

**Estimated Effort:** 1 hour

---

### Phase 1 Summary

| Task | Effort | Deliverable |
|------|--------|-------------|
| 1.1 Configure mypy | 0.5h | mypy.ini or pyproject.toml |
| 1.2 Catalog errors | 1h | Baseline error report |
| 1.3 Fix models/ | 4h | Zero errors in models/ |
| 1.4 Fix triage/ | 6h | Zero errors in triage/ |
| 1.5 Fix classification/ | 6h | Zero errors in classification/ |
| 1.6 Fix remaining | 8h | Zero errors in entire codebase |
| 1.7 Add to CI | 1h | CI/CD integration |
| **TOTAL** | **26.5h** | **100% mypy strict compliance** |

---

## Phase 2: Test Coverage (Weeks 2-3)

### Objective
Achieve 80%+ test coverage on core business logic (triage, classification, screening).

### Setup

**Install coverage tools:**
```bash
pip install pytest pytest-cov
```

**Run coverage baseline:**
```bash
pytest --cov=src/variance --cov-report=html --cov-report=term
```

**Deliverable:** `docs/coverage_baseline.txt` with current coverage %

---

### Tasks

#### 2.1 Unit tests for triage handlers

**Test files to create:**
```
tests/triage/handlers/
├── __init__.py
├── test_expiration_handler.py
├── test_harvest_handler.py
├── test_size_threat_handler.py
├── test_defense_handler.py
├── test_gamma_handler.py
├── test_hedge_handler.py
├── test_toxic_theta_handler.py
├── test_earnings_handler.py
└── test_scalable_handler.py
```

**Template per handler:**
```python
# tests/triage/handlers/test_harvest_handler.py
import pytest
from variance.triage.handlers.harvest import HarvestHandler
from variance.triage.request import TriageRequest, TriageTag
from variance.models.actions import HarvestCommand
from unittest.mock import Mock

class TestHarvestHandler:
    """Unit tests for HarvestHandler."""

    @pytest.fixture
    def default_rules(self):
        """Default rules for testing."""
        return {
            "harvest_target": 0.50,
            "harvest_min_days": 0,
        }

    @pytest.fixture
    def handler(self, default_rules):
        """Create handler instance."""
        return HarvestHandler(default_rules)

    def test_adds_harvest_tag_when_profit_target_hit(self, handler):
        """Should add HARVEST tag when pl_pct >= target."""
        # Arrange
        strategy_obj = Mock()
        strategy_obj.check_harvest.return_value = HarvestCommand(
            symbol="AAPL",
            logic="Profit target hit: 55.0%"
        )

        request = TriageRequest(
            root="AAPL",
            strategy_name="Iron Condor",
            strategy_id="iron_condor",
            dte=30,
            net_pl=550.0,
            net_cost=-100.0,  # Credit position
            strategy_delta=5.0,
            strategy_gamma=0.1,
            pl_pct=0.55,
            days_held=10,
            price=100.0,
            legs=(),
            vrp_structural=1.2,
            vrp_tactical=0.3,
            is_stale=False,
            sector="Technology",
            earnings_date=None,
            portfolio_beta_delta=0.0,
            net_liquidity=10000.0,
            strategy_obj=strategy_obj,
        )

        # Act
        result = handler.handle(request)

        # Assert
        harvest_tags = [t for t in result.tags if t.tag_type == "HARVEST"]
        assert len(harvest_tags) == 1
        assert harvest_tags[0].priority == 10
        assert "55" in harvest_tags[0].logic
        assert harvest_tags[0].action_cmd is not None

    def test_skips_debit_positions(self, handler):
        """Should not tag debit positions."""
        strategy_obj = Mock()
        request = TriageRequest(
            # ... same as above but:
            net_cost=100.0,  # Debit position
            pl_pct=0.55,
            # ...
        )

        result = handler.handle(request)

        harvest_tags = [t for t in result.tags if t.tag_type == "HARVEST"]
        assert len(harvest_tags) == 0

    def test_skips_when_pl_pct_none(self, handler):
        """Should not tag when pl_pct is None."""
        request = TriageRequest(
            net_cost=-100.0,
            pl_pct=None,  # No P/L percentage
            # ...
        )

        result = handler.handle(request)

        harvest_tags = [t for t in result.tags if t.tag_type == "HARVEST"]
        assert len(harvest_tags) == 0

    def test_always_passes_to_next_handler(self, handler):
        """Should always call _pass_to_next (collector pattern)."""
        next_handler = Mock(spec=HarvestHandler)
        next_handler.handle.return_value = Mock()
        handler.set_next(next_handler)

        request = TriageRequest(...)  # Any request

        handler.handle(request)

        # Verify next handler was called
        next_handler.handle.assert_called_once()

    def test_delegates_to_strategy_obj(self, handler):
        """Should delegate harvest check to strategy object."""
        strategy_obj = Mock()
        strategy_obj.check_harvest.return_value = None

        request = TriageRequest(
            net_cost=-100.0,
            pl_pct=0.55,
            strategy_obj=strategy_obj,
            # ...
        )

        handler.handle(request)

        # Verify strategy.check_harvest was called with correct params
        strategy_obj.check_harvest.assert_called_once_with(
            request.root,
            request.pl_pct,
            request.days_held
        )
```

**Coverage target per handler:** 90%+ line coverage

**Deliverables:**
- 9 test files (one per handler)
- 4-5 test cases per handler
- ~40 total test cases

**Acceptance Criteria:**
- ✅ Each handler has 90%+ line coverage
- ✅ Tests cover: happy path, edge cases, collector pattern behavior
- ✅ All tests pass: `pytest tests/triage/handlers/ -v`

**Estimated Effort:** 12 hours (9 handlers × ~1.3h each)

---

#### 2.2 Unit tests for classifiers

**Test files to create:**
```
tests/classification/classifiers/
├── __init__.py
├── test_stock_classifier.py
├── test_single_option_classifier.py
├── test_covered_classifier.py
├── test_strangle_classifier.py
├── test_vertical_classifier.py
├── test_condor_classifier.py
├── test_butterfly_classifier.py
├── test_lizard_classifier.py
├── test_ratio_classifier.py
└── test_multi_exp_classifier.py
```

**Template per classifier:**
```python
# tests/classification/classifiers/test_condor_classifier.py
import pytest
from variance.classification.classifiers.condor import CondorClassifier
from variance.classification.base import ClassificationContext

class TestCondorClassifier:
    """Unit tests for CondorClassifier."""

    @pytest.fixture
    def classifier(self):
        return CondorClassifier()

    def test_identifies_iron_condor(self, classifier):
        """Should identify standard iron condor."""
        legs = [
            {"Call/Put": "Call", "Quantity": "-1", "Strike Price": "100", "Expiration Date": "2025-01-17"},
            {"Call/Put": "Call", "Quantity": "1", "Strike Price": "105", "Expiration Date": "2025-01-17"},
            {"Call/Put": "Put", "Quantity": "-1", "Strike Price": "95", "Expiration Date": "2025-01-17"},
            {"Call/Put": "Put", "Quantity": "1", "Strike Price": "90", "Expiration Date": "2025-01-17"},
        ]
        ctx = ClassificationContext.from_legs(legs)

        assert classifier.can_classify(legs, ctx) is True
        assert classifier.classify(legs, ctx) == "Iron Condor"

    def test_identifies_iron_fly(self, classifier):
        """Should identify iron fly (ATM strikes)."""
        legs = [
            {"Call/Put": "Call", "Quantity": "-1", "Strike Price": "100", "Expiration Date": "2025-01-17"},
            {"Call/Put": "Call", "Quantity": "1", "Strike Price": "105", "Expiration Date": "2025-01-17"},
            {"Call/Put": "Put", "Quantity": "-1", "Strike Price": "100", "Expiration Date": "2025-01-17"},  # Same as short call
            {"Call/Put": "Put", "Quantity": "1", "Strike Price": "95", "Expiration Date": "2025-01-17"},
        ]
        ctx = ClassificationContext.from_legs(legs)

        assert classifier.classify(legs, ctx) == "Iron Fly"

    def test_identifies_dynamic_width_iron_condor(self, classifier):
        """Should identify DWIC (unequal wing widths)."""
        legs = [
            {"Call/Put": "Call", "Quantity": "-1", "Strike Price": "100", "Expiration Date": "2025-01-17"},
            {"Call/Put": "Call", "Quantity": "1", "Strike Price": "110", "Expiration Date": "2025-01-17"},  # 10-wide
            {"Call/Put": "Put", "Quantity": "-1", "Strike Price": "95", "Expiration Date": "2025-01-17"},
            {"Call/Put": "Put", "Quantity": "1", "Strike Price": "90", "Expiration Date": "2025-01-17"},   # 5-wide
        ]
        ctx = ClassificationContext.from_legs(legs)

        assert classifier.classify(legs, ctx) == "Dynamic Width Iron Condor"

    def test_rejects_multi_expiration(self, classifier):
        """Should not classify multi-expiration positions."""
        legs = [
            {"Call/Put": "Call", "Quantity": "-1", "Strike Price": "100", "Expiration Date": "2025-01-17"},
            {"Call/Put": "Call", "Quantity": "1", "Strike Price": "105", "Expiration Date": "2025-02-21"},  # Different exp
            {"Call/Put": "Put", "Quantity": "-1", "Strike Price": "95", "Expiration Date": "2025-01-17"},
            {"Call/Put": "Put", "Quantity": "1", "Strike Price": "90", "Expiration Date": "2025-01-17"},
        ]
        ctx = ClassificationContext.from_legs(legs)

        assert classifier.can_classify(legs, ctx) is False

    def test_rejects_wrong_leg_count(self, classifier):
        """Should not classify positions with != 4 legs."""
        legs = [
            {"Call/Put": "Call", "Quantity": "-1", "Strike Price": "100"},
            {"Call/Put": "Call", "Quantity": "1", "Strike Price": "105"},
        ]
        ctx = ClassificationContext.from_legs(legs)

        assert classifier.can_classify(legs, ctx) is False
```

**Coverage target per classifier:** 90%+ line coverage

**Deliverables:**
- 10 test files (one per classifier)
- 3-5 test cases per classifier
- ~40 total test cases

**Acceptance Criteria:**
- ✅ Each classifier has 90%+ line coverage
- ✅ Tests cover: valid patterns, edge cases, rejection logic
- ✅ All tests pass: `pytest tests/classification/classifiers/ -v`

**Estimated Effort:** 12 hours (10 classifiers × ~1.2h each)

---

#### 2.3 Integration tests for TriageChain

**Test file:** `tests/triage/test_chain_integration.py`

```python
import pytest
from variance.triage.chain import TriageChain
from variance.triage.request import TriageRequest
from datetime import date, timedelta
from unittest.mock import Mock

class TestTriageChainIntegration:
    """Integration tests for full triage chain execution."""

    @pytest.fixture
    def default_rules(self):
        return {
            "gamma_trigger_dte": 21,
            "harvest_target": 0.50,
            "size_threat_threshold": 0.05,
            "earnings_window_days": 7,
            # ... other rules
        }

    @pytest.fixture
    def chain(self, default_rules):
        return TriageChain(default_rules)

    def test_multi_tag_collection(self, chain):
        """Position should collect multiple tags simultaneously."""
        # Arrange: Position that triggers HARVEST, GAMMA, and EARNINGS
        strategy_obj = Mock()
        strategy_obj.check_harvest.return_value = Mock(action_code="HARVEST")

        earnings_date = (date.today() + timedelta(days=5)).isoformat()

        request = TriageRequest(
            root="AAPL",
            strategy_name="Iron Condor",
            strategy_id="iron_condor",
            dte=7,                      # In gamma zone (< 21)
            net_pl=600.0,
            net_cost=-100.0,            # Credit position
            strategy_delta=5.0,
            strategy_gamma=0.1,
            pl_pct=0.60,                # Above harvest target
            days_held=10,
            price=100.0,
            legs=(),
            vrp_structural=1.2,
            vrp_tactical=0.3,
            is_stale=False,
            sector="Technology",
            earnings_date=earnings_date, # Earnings in 5 days
            portfolio_beta_delta=0.0,
            net_liquidity=10000.0,
            strategy_obj=strategy_obj,
        )

        # Act
        result = chain.triage(request)

        # Assert
        tag_types = {t.tag_type for t in result.tags}
        assert "HARVEST" in tag_types, "Should have HARVEST tag"
        assert "GAMMA" in tag_types, "Should have GAMMA tag"
        assert "EARNINGS_WARNING" in tag_types, "Should have EARNINGS_WARNING tag"
        assert len(result.tags) >= 3, "Should have at least 3 tags"

    def test_primary_action_is_highest_priority(self, chain):
        """Primary action should be tag with lowest priority number."""
        # Arrange: Position that triggers both EXPIRING (0) and HARVEST (10)
        strategy_obj = Mock()
        strategy_obj.check_harvest.return_value = Mock(action_code="HARVEST")

        request = TriageRequest(
            dte=0,          # EXPIRING (priority 0)
            pl_pct=0.60,    # HARVEST (priority 10)
            net_cost=-100.0,
            strategy_obj=strategy_obj,
            # ... other fields
        )

        # Act
        result = chain.triage(request)

        # Assert
        assert result.primary_action is not None
        assert result.primary_action.tag_type == "EXPIRING", "EXPIRING should be primary (lower priority number)"

    def test_all_handlers_execute_collector_pattern(self, chain):
        """All 9 handlers should execute (no short-circuiting)."""
        # Arrange: Simple position
        request = TriageRequest(
            dte=30,
            pl_pct=0.20,
            net_cost=-100.0,
            # ... minimal fields
        )

        # Act
        result = chain.triage(request)

        # Assert: Chain should complete without error
        # Even if no tags added, all handlers should have been called
        assert result is not None
        # We can't easily verify all handlers called without spies,
        # but we verify the chain completes successfully

    def test_empty_tags_when_no_conditions_met(self, chain):
        """Should have no tags when no conditions are met."""
        strategy_obj = Mock()
        strategy_obj.check_harvest.return_value = None

        request = TriageRequest(
            dte=45,         # Not in gamma zone
            pl_pct=0.10,    # Below harvest target
            net_cost=-100.0,
            earnings_date=None,
            strategy_obj=strategy_obj,
            # ... other fields with no triggers
        )

        result = chain.triage(request)

        assert len(result.tags) == 0
        assert result.primary_action is None

    def test_size_threat_overrides_harvest(self, chain):
        """SIZE_THREAT (priority 20) should be primary over GAMMA (priority 40)."""
        strategy_obj = Mock()

        request = TriageRequest(
            dte=10,                     # GAMMA zone
            net_pl=600.0,
            net_cost=-100.0,
            net_liquidity=10000.0,
            # Size threat: 600 / 10000 = 6% > 5% threshold
            strategy_obj=strategy_obj,
            # ... other fields
        )

        result = chain.triage(request)

        tag_types = {t.tag_type for t in result.tags}
        if "SIZE_THREAT" in tag_types:
            # SIZE_THREAT should be primary over GAMMA
            assert result.primary_action.tag_type == "SIZE_THREAT"
```

**Deliverables:**
- 1 integration test file
- 8-10 test scenarios
- Tests cover multi-tag scenarios, priority ordering, edge cases

**Acceptance Criteria:**
- ✅ All integration tests pass
- ✅ Coverage of multi-tag logic
- ✅ Tests validate collector pattern (all handlers execute)

**Estimated Effort:** 6 hours

---

#### 2.4 Integration tests for ScreeningPipeline

**Test file:** `tests/screening/test_pipeline_integration.py`

```python
import pytest
from variance.screening.pipeline import ScreeningPipeline
from variance.config_loader import load_config_bundle
from unittest.mock import patch, Mock

class TestScreeningPipelineIntegration:
    """Integration tests for ScreeningPipeline."""

    @pytest.fixture
    def config_bundle(self):
        """Load real config bundle."""
        return load_config_bundle(strict=False)

    @pytest.fixture
    def mock_config(self):
        """Mock screener config."""
        from variance.vol_screener import ScreenerConfig
        return ScreenerConfig(limit=10, signal_filter=None)

    def test_full_pipeline_execution(self, mock_config, config_bundle):
        """Pipeline should execute all 6 steps."""
        # Mock yfinance to avoid network calls
        with patch('variance.screening.steps.fetch.yf') as mock_yf:
            mock_yf.Ticker.return_value.history.return_value = Mock()
            mock_yf.Ticker.return_value.option_chain.return_value = Mock()

            pipeline = ScreeningPipeline(mock_config, config_bundle)
            result = pipeline.execute()

        assert "candidates" in result
        assert "summary" in result
        assert isinstance(result["candidates"], list)

    def test_enrichment_strategies_applied(self, mock_config, config_bundle):
        """All enrichment strategies should add calculated fields."""
        with patch('variance.screening.steps.fetch.yf') as mock_yf:
            # Mock market data
            mock_yf.Ticker.return_value.history.return_value = Mock(
                Close=[100, 102, 101],
                # ... mock data
            )

            pipeline = ScreeningPipeline(mock_config, config_bundle)
            result = pipeline.execute()

        if result["candidates"]:
            candidate = result["candidates"][0]
            # VrpEnrichmentStrategy should add these
            assert "Compression Ratio" in candidate
            assert "VRP_Tactical_Markup" in candidate
            assert "Signal" in candidate

            # ScoreEnrichmentStrategy should add this
            assert "Variance_Score" in candidate or "variance_score" in candidate

    @pytest.mark.slow
    def test_real_market_data_fetch(self, mock_config, config_bundle):
        """Test with real yfinance API (slow, integration test)."""
        # This test actually calls yfinance
        # Mark with @pytest.mark.slow and run separately

        # Limit to just 1 ticker for speed
        mock_config.limit = 1

        pipeline = ScreeningPipeline(mock_config, config_bundle)
        result = pipeline.execute()

        assert result is not None
        assert "candidates" in result
```

**Deliverables:**
- 1 integration test file
- 5-7 test scenarios
- Mix of mocked and real API tests

**Acceptance Criteria:**
- ✅ All tests pass
- ✅ Fast tests use mocks
- ✅ Slow tests marked with `@pytest.mark.slow`

**Estimated Effort:** 5 hours

---

#### 2.5 Configure coverage reporting

**File:** `pyproject.toml` or `.coveragerc`

```toml
[tool.coverage.run]
source = ["src/variance"]
omit = [
    "*/tests/*",
    "*/test_*.py",
    "*/__pycache__/*",
    "*/venv/*",
]

[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    "def __repr__",
    "raise AssertionError",
    "raise NotImplementedError",
    "if __name__ == .__main__.:",
    "if TYPE_CHECKING:",
    "@abstractmethod",
]
```

**Add coverage to CI:**
```yaml
- name: Run tests with coverage
  run: |
    pytest --cov=src/variance --cov-report=xml --cov-report=term-missing

- name: Upload coverage to Codecov (optional)
  uses: codecov/codecov-action@v3
  with:
    file: ./coverage.xml
```

**Deliverable:** Coverage reports in CI

**Acceptance Criteria:**
- ✅ Coverage measured on every CI run
- ✅ Coverage badge in README (optional)
- ✅ CI fails if coverage drops below 75%

**Estimated Effort:** 2 hours

---

### Phase 2 Summary

| Task | Effort | Deliverable |
|------|--------|-------------|
| 2.1 Handler tests | 12h | ~40 handler tests |
| 2.2 Classifier tests | 12h | ~40 classifier tests |
| 2.3 Triage integration | 6h | 8-10 integration tests |
| 2.4 Screening integration | 5h | 5-7 integration tests |
| 2.5 Coverage config | 2h | CI coverage reporting |
| **TOTAL** | **37h** | **80%+ coverage** |

---

## Phase 3: Documentation (Weeks 3-4)

### Objective
Create onboarding documentation for future developers and contractors.

### Tasks

#### 3.1 Write ADR: Hybrid FP+OOP Architecture

**File:** `docs/adr/ADR_019_HYBRID_FUNCTIONAL_OOP.md`

**Template:**
```markdown
# ADR 019: Hybrid Functional + OOP Architecture

## Status
Accepted

## Context
The Variance codebase uses a hybrid approach combining functional programming
principles with object-oriented design patterns. This decision was made to
balance Python idioms with functional programming benefits (immutability,
composability, testability).

## Decision

### Functional Core
We use functional programming principles for data transformation:

1. **Immutable data structures** - All domain objects are frozen dataclasses
   ```python
   @dataclass(frozen=True)
   class TriageRequest:
       ...
   ```

2. **Pure transformations** - Handlers/enrichers return new objects
   ```python
   def handle(self, request: TriageRequest) -> TriageRequest:
       return request.with_tag(tag)  # Returns new instance
   ```

3. **Composable specifications** - Market filters compose with operators
   ```python
   combined = liquid_spec & vrp_spec & ~sector_exclusion
   ```

4. **Explicit data flow** - All state passed as function parameters

### OOP Shell
We use object-oriented patterns for organization and extensibility:

1. **Abstract Base Classes** - Define contracts via ABCs
   - `TriageHandler` (9 concrete implementations)
   - `StrategyClassifier` (10 concrete implementations)
   - `BaseStrategy` (4 concrete implementations)
   - `EnrichmentStrategy` (2 concrete implementations)

2. **Chain of Responsibility** - Sequential processing with clear priority
   - Triage handlers execute in priority order
   - Classifiers execute until match found

3. **Template Method** - Fixed algorithm skeleton with hooks
   - `ScreeningPipeline.execute()` defines 6-step process
   - `ClusteringPipeline.cluster()` defines clustering flow

4. **Registry Pattern** - Self-registering strategies
   ```python
   @BaseStrategy.register("short_vol")
   class ShortThetaStrategy(BaseStrategy):
       ...
   ```

## Rationale

### Why Not Pure Functional?
- Python lacks strong FP features (no TCO, weak type system pre-3.10)
- Team familiarity with OOP patterns
- OOP provides clear extension points ("add a handler class")

### Why Not Pure OOP?
- Mutable state leads to bugs
- Harder to test with side effects
- Less composable than pure functions

### Why Hybrid?
- Best of both worlds
- Immutability prevents bugs
- Clear class structure aids discovery
- Testable and maintainable

## Consequences

### Positive
- **Testable:** Pure functions + small classes = easy unit tests
- **Extensible:** Add handler/classifier via subclass + registry
- **Type-safe:** Works well with mypy strict mode
- **Composable:** Specifications and pipelines compose naturally
- **Maintainable:** Changes localized to specific handlers

### Negative
- **Two paradigms:** Team must understand both FP and OOP
- **More files:** 30+ handler/classifier files vs monolithic functions
- **Discipline required:** Must maintain immutability conventions

## References
- RFC_016: Chain of Responsibility for Triage Engine
- RFC_017: Template Method + Strategy for Screening Pipeline
- RFC_018: Registry Pattern for Strategy Detection
- [Functional Core, Imperative Shell](https://www.destroyallsoftware.com/screencasts/catalog/functional-core-imperative-shell)
```

**Deliverable:** Complete ADR document

**Acceptance Criteria:**
- ✅ ADR explains rationale for hybrid approach
- ✅ Provides concrete code examples
- ✅ Documents trade-offs
- ✅ References relevant RFCs

**Estimated Effort:** 3 hours

---

#### 3.2 Create "How to Add a Triage Handler" guide

**File:** `docs/guides/adding_triage_handler.md`

**Template:** (See full example in previous message - I'll include abbreviated version here)

```markdown
# How to Add a Triage Handler

## Overview
Triage handlers detect specific conditions and tag positions with actionable
recommendations or warnings. They execute in priority order via the Chain of
Responsibility pattern.

## When to Add a Handler
Create a new handler when you need to:
- Detect a new risk condition (e.g., "vega exposure too high")
- Identify a new opportunity (e.g., "vol crush expected post-earnings")
- Add a new warning (e.g., "dividend date approaching")

## Step-by-Step Guide

### Step 1: Create Handler File

**Location:** `src/variance/triage/handlers/your_handler_name.py`

**Template:**
```python
from ..handler import TriageHandler
from ..request import TriageRequest, TriageTag
from typing import Optional

class YourHandlerName(TriageHandler):
    """
    Detects [CONDITION] and tags positions.

    Priority: [NUMBER] (see priority guidelines below)
    Actionable: [Yes/No]
    """

    def __init__(self, rules: dict[str, Any]) -> None:
        """
        Initialize handler with trading rules.

        Args:
            rules: Dictionary of trading rules from config
        """
        super().__init__(rules)
        self.threshold = rules.get("your_threshold_key", default_value)

    def handle(self, request: TriageRequest) -> TriageRequest:
        """
        Check condition and add tag if triggered.

        Args:
            request: Immutable triage request with position metrics

        Returns:
            New TriageRequest with tag added (if condition met)
        """
        # Check your condition
        if self._should_tag(request):
            tag = TriageTag(
                tag_type="YOUR_TAG_NAME",
                priority=YOUR_PRIORITY,  # See priority table below
                logic=self._build_logic_message(request),
                action_cmd=None  # Or ActionCommand if actionable
            )
            request = request.with_tag(tag)

        # ALWAYS pass to next (collector pattern)
        return self._pass_to_next(request)

    def _should_tag(self, request: TriageRequest) -> bool:
        """Check if condition is met."""
        # Your logic here
        return request.some_metric > self.threshold

    def _build_logic_message(self, request: TriageRequest) -> str:
        """Build human-readable explanation."""
        return f"Your condition met: {request.some_metric:.2f}"
```

### Step 2: Register Handler in Chain

**Location:** `src/variance/triage/chain.py`

**Add import:**
```python
from .handlers.your_handler_name import YourHandlerName
```

**Add to chain (in priority order):**
```python
def _build_chain(self) -> None:
    """Builds the chain from registered handlers, sorted by priority."""
    handlers = [
        ExpirationHandler(self.rules),
        HarvestHandler(self.rules),
        # ... existing handlers in priority order ...
        YourHandlerName(self.rules),  # Add here (in priority order)
        # ... remaining handlers ...
    ]

    if not handlers:
        return

    self._head = handlers[0]
    current = self._head
    for handler in handlers[1:]:
        current = current.set_next(handler)
```

### Step 3: Add Configuration (Optional)

**Location:** `config/trading_rules.json`

```json
{
  "your_threshold_key": 0.75,
  "your_other_config": true
}
```

### Step 4: Write Tests

**Location:** `tests/triage/handlers/test_your_handler_name.py`

```python
import pytest
from variance.triage.handlers.your_handler_name import YourHandlerName
from variance.triage.request import TriageRequest

class TestYourHandlerName:
    @pytest.fixture
    def handler(self):
        rules = {"your_threshold_key": 0.75}
        return YourHandlerName(rules)

    def test_adds_tag_when_condition_met(self, handler):
        request = TriageRequest(some_metric=0.80, ...)
        result = handler.handle(request)

        tags = [t for t in result.tags if t.tag_type == "YOUR_TAG_NAME"]
        assert len(tags) == 1

    def test_skips_when_condition_not_met(self, handler):
        request = TriageRequest(some_metric=0.50, ...)
        result = handler.handle(request)

        tags = [t for t in result.tags if t.tag_type == "YOUR_TAG_NAME"]
        assert len(tags) == 0
```

## Priority Guidelines

| Priority | Category | When to Use | Examples |
|----------|----------|-------------|----------|
| 0-10 | Critical Actions | Position MUST be acted on immediately | EXPIRING, HARVEST |
| 20-30 | High Priority | Position needs attention soon | SIZE_THREAT, DEFENSE |
| 40-50 | Warnings | Position should be monitored | GAMMA, HEDGE_CHECK |
| 60-80 | Informational | Nice-to-know info | TOXIC, EARNINGS_WARNING |
| 90-100 | Opportunities | Optional actions | SCALABLE, custom |

**Lower priority number = higher urgency in TUI display**

## Collector Pattern (Important!)

All handlers MUST follow the collector pattern:

✅ **DO:**
```python
def handle(self, request):
    if condition:
        request = request.with_tag(tag)
    return self._pass_to_next(request)  # ALWAYS call this
```

❌ **DON'T:**
```python
def handle(self, request):
    if condition:
        return request.with_tag(tag)  # WRONG: Breaks chain
    return self._pass_to_next(request)
```

## Complete Example

See `src/variance/triage/handlers/gamma.py` for a simple, complete example.

## Questions?

Contact: [Your team contact]
```

**Deliverable:** Complete guide with examples

**Acceptance Criteria:**
- ✅ Step-by-step instructions
- ✅ Complete code templates
- ✅ Priority guidelines
- ✅ Testing instructions

**Estimated Effort:** 4 hours

---

#### 3.3 Create "How to Add a Classifier" guide

**File:** `docs/guides/adding_classifier.md`

**Similar structure to handler guide:**
- Overview of ClassifierChain
- Step-by-step: create classifier, register, test
- Pattern matching examples
- Priority order guidelines

**Deliverable:** Complete guide

**Acceptance Criteria:**
- ✅ Clear instructions for adding classifiers
- ✅ Code templates
- ✅ Testing examples

**Estimated Effort:** 4 hours

---

#### 3.4 Document Multi-Tag System

**File:** `docs/guides/multi_tag_system.md`

```markdown
# Multi-Tag Triage System

## Overview
The triage system applies **multiple tags** to each position, providing
comprehensive health assessment. A position can simultaneously be:
- ✅ **HARVEST** - Profit target hit
- ⚠️ **GAMMA** - Approaching expiration
- 📅 **EARNINGS_WARNING** - Earnings event soon

## How It Works

### Collector Pattern
Unlike traditional Chain of Responsibility (first match wins), our triage
chain uses a **collector pattern** where ALL handlers execute:

```
Position → [Expiration] → [Harvest] → [Gamma] → [Earnings] → ... → Result
            ↓ May tag     ↓ May tag    ↓ May tag   ↓ May tag

Result.tags = [HARVEST, GAMMA, EARNINGS_WARNING]
```

### Primary vs Secondary Tags
- **Primary Tag:** Highest priority (lowest priority number)
- **Secondary Tags:** All other tags, sorted by priority

**Example:**
```json
{
  "root": "AAPL",
  "primary_action": {
    "tag_type": "HARVEST",
    "priority": 10,
    "logic": "Profit target hit: 55%"
  },
  "tags": [
    {"tag_type": "HARVEST", "priority": 10},
    {"tag_type": "GAMMA", "priority": 40},
    {"tag_type": "EARNINGS_WARNING", "priority": 70}
  ]
}
```

## TUI Rendering

### Current Implementation
Primary action shown in `action_code` field (backward compatible).

### Future Implementation (Phase 4)
Multi-tag badges in terminal:
```
┌────────────────────────────────────────────────────────┐
│ AAPL  Iron Condor  45 DTE  $1,250 P/L                │
│ [🎯 HARVEST 55%] [⚠️ GAMMA] [📅 EARNINGS 3d]          │
└────────────────────────────────────────────────────────┘
```

## Filtering & Sorting

### Filter by Tag
```python
# Get all positions with GAMMA tag
gamma_positions = [
    p for p in positions
    if any(t["type"] == "GAMMA" for t in p["tags"])
]
```

### Sort by Priority
```python
# Sort by primary tag priority (most urgent first)
sorted_positions = sorted(
    positions,
    key=lambda p: p["tags"][0]["priority"] if p["tags"] else 999
)
```

### Multi-Tag Queries
```python
# Positions with both HARVEST and EARNINGS
risky_harvests = [
    p for p in positions
    if {"HARVEST", "EARNINGS_WARNING"} <= {t["type"] for t in p["tags"]}
]
```

## Configuration

Tags can be hidden or customized in `config/trading_rules.json`:

```json
{
  "triage_display": {
    "max_secondary_tags": 3,
    "hide_tags": ["HEDGE_CHECK"],
    "tag_colors": {
      "HARVEST": "green",
      "DEFENSE": "yellow"
    }
  }
}
```

## API Reference

### TriageTag
```python
@dataclass(frozen=True)
class TriageTag:
    tag_type: str           # "HARVEST", "GAMMA", etc.
    priority: int           # Lower = higher priority
    logic: str              # Human-readable reason
    action_cmd: Optional[ActionCommand]  # Optional command
```

### TriageRequest
```python
@dataclass(frozen=True)
class TriageRequest:
    # ... metrics ...
    tags: tuple[TriageTag, ...] = ()

    @property
    def primary_action(self) -> Optional[TriageTag]:
        """Returns highest-priority tag."""
        return min(self.tags, key=lambda t: t.priority) if self.tags else None
```

## Examples

See `tests/triage/test_chain_integration.py` for comprehensive examples.
```

**Deliverable:** Complete multi-tag documentation

**Acceptance Criteria:**
- ✅ Explains collector pattern
- ✅ Shows filtering/sorting examples
- ✅ Documents API

**Estimated Effort:** 3 hours

---

### Phase 3 Summary

| Task | Effort | Deliverable |
|------|--------|-------------|
| 3.1 ADR (hybrid arch) | 3h | ADR_019 |
| 3.2 Handler guide | 4h | adding_triage_handler.md |
| 3.3 Classifier guide | 4h | adding_classifier.md |
| 3.4 Multi-tag guide | 3h | multi_tag_system.md |
| **TOTAL** | **14h** | **4 documentation files** |

---

## Phase 4: Multi-Tag TUI Rendering (Weeks 5-6)

### Objective
Make multi-tag system visible in terminal UI with color-coded badges.

### Tasks

#### 4.1 Design TUI Multi-Tag Rendering

**Deliverable:** Mock-ups and design document

**File:** `docs/tui_mockups/multi_tag_rendering.md`

**Contents:**

```markdown
# Multi-Tag TUI Rendering Design

## Current State
```
┌─────────────────────────────────────────────────┐
│ Symbol  Strategy        DTE  P/L    Action      │
├─────────────────────────────────────────────────┤
│ AAPL    Iron Condor      45  $1250  HARVEST     │
│ TSLA    Short Strangle   12  -$200  DEFENSE     │
└─────────────────────────────────────────────────┘
```

Single action code, no context on other conditions.

## Proposed Design (Option A: Badge Style)

```
┌──────────────────────────────────────────────────────────────┐
│ Symbol  Strategy         DTE   P/L    Tags                   │
├──────────────────────────────────────────────────────────────┤
│ AAPL    Iron Condor       45  $1250  🎯 HARVEST │ ⚠️ GAMMA    │
│ TSLA    Short Strangle    12  -$200  🔴 DEFENSE │ 📅 EARNINGS │
└──────────────────────────────────────────────────────────────┘

Color codes:
  🎯 Green   - Actionable positive (HARVEST, SCALABLE)
  🔴 Red     - Critical action needed (EXPIRING, DEFENSE, SIZE_THREAT)
  ⚠️ Yellow  - Warning (GAMMA, TOXIC)
  📅 Orange  - Informational (EARNINGS, HEDGE_CHECK)
```

## Proposed Design (Option B: Inline Compact)

```
┌────────────────────────────────────────────────────┐
│ AAPL IC  45d  $1,250  [🎯55%][⚠️γ][📅3d]          │
│ TSLA SS  12d   -$200  [🔴DEF][📅ERN]              │
└────────────────────────────────────────────────────┘

Abbreviations:
  🎯55% = HARVEST at 55% profit
  ⚠️γ   = GAMMA zone
  📅3d  = EARNINGS in 3 days
  🔴DEF = DEFENSE needed
```

## Proposed Design (Option C: Detailed Rows)

```
┌────────────────────────────────────────────────────────────────┐
│ AAPL  Iron Condor  45 DTE  $1,250 P/L                         │
│ PRIMARY: 🎯 HARVEST (Profit target: 55%)                       │
│ ALSO:    ⚠️ GAMMA (Entering gamma zone)                       │
│          📅 EARNINGS (Event in 3 days)                         │
├────────────────────────────────────────────────────────────────┤
│ TSLA  Short Strangle  12 DTE  -$200 P/L                       │
│ PRIMARY: 🔴 DEFENSE (Position tested, roll needed)             │
│ ALSO:    📅 EARNINGS (Event tomorrow)                          │
└────────────────────────────────────────────────────────────────┘
```

## Recommendation: Option A (Badge Style)

**Pros:**
- Compact (fits in standard terminal width)
- Clear visual hierarchy (primary badge larger/bolded)
- Up to 3-4 tags visible per row
- Color-coded for quick scanning

**Cons:**
- May truncate on very narrow terminals
- Requires Unicode support (emojis)

**Implementation:**
- Use `rich` library's `Text` with markup
- Primary tag: Bold, larger or bordered
- Secondary tags: Normal size, muted color
- Fallback for no-emoji terminals: `[H]`, `[G]`, `[E]`
```

**Acceptance Criteria:**
- ✅ 3 design options presented
- ✅ Pros/cons for each
- ✅ Recommendation with rationale
- ✅ Fallback plan for limited terminals

**Estimated Effort:** 3 hours

---

#### 4.2 Implement Multi-Tag Display

**Files to modify:**
- `src/variance/tui_renderer.py`
- Create: `src/variance/tui/tag_renderer.py` (optional helper)

**Implementation:**

```python
# src/variance/tui/tag_renderer.py
from rich.text import Text
from typing import Optional

class TagRenderer:
    """Renders triage tags as colored badges for TUI."""

    TAG_ICONS = {
        "EXPIRING": "🔴",
        "HARVEST": "🎯",
        "SIZE_THREAT": "⚠️",
        "DEFENSE": "🔴",
        "GAMMA": "⚠️",
        "HEDGE_CHECK": "👁️",
        "TOXIC": "⚠️",
        "EARNINGS_WARNING": "📅",
        "SCALABLE": "🚀",
    }

    TAG_COLORS = {
        "EXPIRING": "red bold",
        "HARVEST": "green bold",
        "SIZE_THREAT": "red",
        "DEFENSE": "red bold",
        "GAMMA": "yellow",
        "HEDGE_CHECK": "cyan",
        "TOXIC": "yellow",
        "EARNINGS_WARNING": "orange3",
        "SCALABLE": "green",
    }

    def __init__(self, config: dict[str, Any]):
        """
        Initialize renderer with config.

        Args:
            config: Display config from trading_rules.json
        """
        self.max_secondary = config.get("max_secondary_tags", 3)
        self.hide_tags = set(config.get("hide_tags", []))
        self.use_icons = config.get("use_icons", True)

    def render_tags(self, tags: list[dict]) -> Text:
        """
        Render tags as colored badges.

        Args:
            tags: List of tag dicts with 'type', 'priority', 'logic'

        Returns:
            Rich Text object with formatted badges
        """
        if not tags:
            return Text("-", style="dim")

        # Filter hidden tags
        visible_tags = [
            t for t in tags
            if t["type"] not in self.hide_tags
        ]

        if not visible_tags:
            return Text("-", style="dim")

        # Primary tag (first, highest priority)
        primary = visible_tags[0]
        result = self._render_primary_badge(primary)

        # Secondary tags (up to max_secondary)
        for tag in visible_tags[1:self.max_secondary + 1]:
            result.append(" ")
            result.append(self._render_secondary_badge(tag))

        return result

    def _render_primary_badge(self, tag: dict) -> Text:
        """Render primary tag badge (bold, with icon)."""
        tag_type = tag["type"]
        icon = self.TAG_ICONS.get(tag_type, "•") if self.use_icons else ""
        color = self.TAG_COLORS.get(tag_type, "white")

        # Extract short value from logic if available
        # e.g., "Profit target hit: 55%" -> "55%"
        short_val = self._extract_value(tag.get("logic", ""))

        label = f"{icon} {tag_type}"
        if short_val:
            label += f" {short_val}"

        return Text(label, style=color)

    def _render_secondary_badge(self, tag: dict) -> Text:
        """Render secondary tag badge (muted)."""
        tag_type = tag["type"]
        icon = self.TAG_ICONS.get(tag_type, "•") if self.use_icons else ""
        color = self.TAG_COLORS.get(tag_type, "white") + " dim"

        # Abbreviated label for secondary tags
        abbrev = self._abbreviate(tag_type)
        label = f"{icon}{abbrev}" if icon else abbrev

        return Text(label, style=color)

    def _extract_value(self, logic: str) -> Optional[str]:
        """Extract short value from logic string."""
        # "Profit target hit: 55%" -> "55%"
        import re
        match = re.search(r'(\d+\.?\d*%)', logic)
        return match.group(1) if match else None

    def _abbreviate(self, tag_type: str) -> str:
        """Abbreviate tag type for compact display."""
        abbrevs = {
            "GAMMA": "γ",
            "EARNINGS_WARNING": "ERN",
            "HEDGE_CHECK": "HDG",
            "SIZE_THREAT": "SIZE",
        }
        return abbrevs.get(tag_type, tag_type[:3])
```

**Modify `tui_renderer.py`:**

```python
# src/variance/tui_renderer.py
from .tui.tag_renderer import TagRenderer

class TUIRenderer:
    def __init__(self, config: dict):
        self.config = config
        self.tag_renderer = TagRenderer(
            config.get("triage_display", {})
        )

    def render_position_row(self, position: dict) -> tuple:
        """Render a single position row with multi-tag support."""
        # Existing columns
        symbol = position["root"]
        strategy = position["strategy_name"]
        dte = position.get("dte", "-")
        pnl = position.get("net_pl", 0.0)

        # NEW: Render tags
        tags = position.get("tags", [])
        tag_display = self.tag_renderer.render_tags(tags)

        return (symbol, strategy, dte, f"${pnl:,.0f}", tag_display)
```

**Deliverable:** Working multi-tag rendering in TUI

**Acceptance Criteria:**
- ✅ Primary tag displayed with icon and color
- ✅ Up to 3 secondary tags shown (muted)
- ✅ Color-coded by priority
- ✅ Configurable via `trading_rules.json`
- ✅ Fallback for no-emoji terminals
- ✅ Works in standard 80-column terminal

**Estimated Effort:** 10 hours

---

#### 4.3 Add Tag Configuration

**File:** `config/trading_rules.json`

**Add section:**
```json
{
  "triage_display": {
    "max_secondary_tags": 3,
    "use_icons": true,
    "hide_tags": [],
    "tag_colors": {
      "HARVEST": "green bold",
      "DEFENSE": "red bold",
      "GAMMA": "yellow",
      "EARNINGS_WARNING": "orange3"
    },
    "tag_icons": {
      "HARVEST": "🎯",
      "GAMMA": "⚠️",
      "EARNINGS_WARNING": "📅",
      "DEFENSE": "🔴"
    }
  }
}
```

**Validation:**
- Create JSON schema for config validation
- Add config loader tests

**Deliverable:** Configurable tag display

**Acceptance Criteria:**
- ✅ Users can customize colors
- ✅ Users can hide specific tags
- ✅ Users can disable icons
- ✅ Sane defaults if config missing

**Estimated Effort:** 3 hours

---

#### 4.4 Update Documentation

**Update files:**
- `docs/guides/multi_tag_system.md` (add TUI screenshots)
- `README.md` (add screenshot of new TUI)
- `docs/configuration.md` (document triage_display settings)

**Deliverable:** Updated docs with examples

**Acceptance Criteria:**
- ✅ Screenshots of TUI with multi-tags
- ✅ Configuration examples
- ✅ Migration guide from old TUI

**Estimated Effort:** 2 hours

---

### Phase 4 Summary

| Task | Effort | Deliverable |
|------|--------|-------------|
| 4.1 Design mockups | 3h | TUI design document |
| 4.2 Implement rendering | 10h | Working multi-tag TUI |
| 4.3 Add configuration | 3h | Configurable tags |
| 4.4 Update docs | 2h | Screenshots + guides |
| **TOTAL** | **18h** | **User-facing feature** |

---

## Phase 5: Performance Profiling (Week 7, CONDITIONAL)

### Objective
Profile screening pipeline and optimize ONLY if performance issues exist.

**IMPORTANT:** Only execute this phase if profiling reveals issues (>5s for 100 tickers).

### Tasks

#### 5.1 Profile Screening Pipeline

**Run profiling:**
```bash
# Profile with cProfile
python -m cProfile -o screening.prof -m variance.screen \
  --limit 100 \
  --config-dir config/

# Analyze with snakeviz (visual)
pip install snakeviz
snakeviz screening.prof

# Or use pstats (text)
python -c "
import pstats
p = pstats.Stats('screening.prof')
p.sort_stats('cumulative')
p.print_stats(20)  # Top 20 functions
"
```

**Document results:**

**File:** `docs/performance/screening_profile_baseline.md`

```markdown
# Screening Pipeline Performance Baseline

## Test Setup
- Date: [DATE]
- Machine: [SPECS]
- Python: [VERSION]
- Limit: 100 tickers
- Config: Default trading rules

## Results

### Overall Metrics
- **Total Runtime:** [X.XX] seconds
- **Tickers/Second:** [XX.X]
- **Target:** < 2 seconds for 100 tickers

### Time Breakdown by Step

| Step | Time (s) | % Total |
|------|----------|---------|
| load_symbols | 0.05 | 2% |
| fetch_data | 4.20 | 84% |
| filter_candidates | 0.30 | 6% |
| enrich_candidates | 0.25 | 5% |
| sort_and_dedupe | 0.10 | 2% |
| build_report | 0.05 | 1% |

### Top 10 Hotspots

| Function | Calls | Time (s) | % Total |
|----------|-------|----------|---------|
| yfinance.Ticker.history | 100 | 2.50 | 50% |
| yfinance.Ticker.option_chain | 100 | 1.70 | 34% |
| calculate_vrp_tactical | 73 | 0.15 | 3% |
| ... | ... | ... | ... |

## Decision Point

**IF Total Runtime > 5 seconds:** Proceed to optimization (Task 5.2)
**IF Total Runtime < 5 seconds:** Skip optimization, performance acceptable

**Actual Runtime:** [X.XX] seconds
**Decision:** [OPTIMIZE / SKIP]
```

**Deliverable:** Profiling report with decision

**Acceptance Criteria:**
- ✅ Profiling data collected
- ✅ Hotspots identified
- ✅ Decision documented (optimize or skip)

**Estimated Effort:** 3 hours

---

#### 5.2 Optimize Bottlenecks (CONDITIONAL)

**Only execute if Task 5.1 shows Total Runtime > 5 seconds**

**Common optimizations:**

##### A. Parallelize yfinance Fetching

**Problem:** Sequential fetching takes 4+ seconds

**Solution:** Use asyncio or threading

```python
# src/variance/screening/steps/fetch.py
import concurrent.futures
from typing import Dict

def fetch_market_data_parallel(symbols: list[str]) -> Dict[str, dict]:
    """Fetch market data in parallel using ThreadPoolExecutor."""

    def fetch_single(symbol: str) -> tuple[str, dict]:
        """Fetch data for a single ticker."""
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="1y")
            options = ticker.option_chain(ticker.options[0]) if ticker.options else None
            # ... extract metrics ...
            return (symbol, metrics)
        except Exception as e:
            logger.warning(f"Failed to fetch {symbol}: {e}")
            return (symbol, None)

    # Use ThreadPoolExecutor (GIL released during I/O)
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(fetch_single, sym): sym for sym in symbols}
        results = {}

        for future in concurrent.futures.as_completed(futures):
            symbol, data = future.result()
            if data:
                results[symbol] = data

    return results
```

**Expected Improvement:** 4.2s → 0.8s (80% reduction)

---

##### B. Cache Expensive Calculations

**Problem:** VRP calculation repeated for same inputs

**Solution:** Use `@lru_cache`

```python
# src/variance/screening/enrichment/vrp.py
from functools import lru_cache

class VrpEnrichmentStrategy(EnrichmentStrategy):

    @staticmethod
    @lru_cache(maxsize=1000)
    def _calculate_vrp_tactical(
        iv30: float,
        hv20: float,
        hv_floor: float
    ) -> float:
        """Calculate VRP tactical markup (cached)."""
        hv_floor_actual = max(hv20, hv_floor)
        raw_markup = (iv30 - hv_floor_actual) / hv_floor_actual
        return max(-0.99, min(3.0, raw_markup))
```

**Expected Improvement:** 0.15s → 0.02s (87% reduction)

---

##### C. Lazy Enrichment

**Problem:** Enriching all candidates, even those filtered out

**Solution:** Enrich only top N after sorting

```python
# src/variance/screening/pipeline.py

def _enrich_candidates(self) -> None:
    """Step 4: Enrich candidates (LAZY - only top candidates)."""
    # Pre-sort by signal strength (lightweight)
    self.ctx.candidates = sorted(
        self.ctx.candidates,
        key=lambda c: c.get("IV30", 0),  # Simple sort
        reverse=True
    )

    # Only enrich top 50 (or config limit)
    top_n = min(50, self.ctx.config.limit * 2)
    candidates_to_enrich = self.ctx.candidates[:top_n]

    # Apply enrichment strategies
    for strategy in self._enrichment_strategies:
        for candidate in candidates_to_enrich:
            strategy.enrich(candidate, self.ctx)

    # Update context with enriched subset
    self.ctx.candidates = candidates_to_enrich
```

**Expected Improvement:** 0.25s → 0.05s (80% reduction)

---

**Deliverable:** Optimized screening pipeline

**Acceptance Criteria:**
- ✅ Total runtime < 2 seconds for 100 tickers
- ✅ All tests still pass (no accuracy loss)
- ✅ Performance documented in `docs/performance/`

**Estimated Effort:** 8 hours (conditional on profiling results)

---

### Phase 5 Summary

| Task | Effort | Deliverable | Conditional |
|------|--------|-------------|-------------|
| 5.1 Profile pipeline | 3h | Profiling report | Required |
| 5.2 Optimize (if needed) | 8h | <2s runtime | Only if >5s baseline |
| **TOTAL** | **3-11h** | **Performance report** | Conditional |

---

## Project Summary

### Total Effort Estimate

| Phase | Duration | Effort | Priority |
|-------|----------|--------|----------|
| **Phase 1: Type Safety** | Week 1 | 26.5h | 🔴 HIGH |
| **Phase 2: Test Coverage** | Week 2-3 | 37h | 🔴 HIGH |
| **Phase 3: Documentation** | Week 3-4 | 14h | 🟡 MED |
| **Phase 4: Multi-Tag TUI** | Week 5-6 | 18h | 🔴 HIGH |
| **Phase 5: Performance** | Week 7 | 3-11h | 🟢 LOW |
| **TOTAL** | **6-7 weeks** | **98.5-106.5h** | |

**Average: ~102 hours = 2.5 weeks full-time**

---

## Deliverables Checklist

### Phase 1: Type Safety
- [ ] `mypy.ini` or `pyproject.toml` with strict config
- [ ] `docs/type_errors_baseline.txt`
- [ ] Zero mypy errors in `src/variance/`
- [ ] CI/CD runs mypy on every commit

### Phase 2: Test Coverage
- [ ] 40+ unit tests for triage handlers
- [ ] 40+ unit tests for classifiers
- [ ] 15+ integration tests
- [ ] Coverage reports in CI
- [ ] 80%+ coverage achieved

### Phase 3: Documentation
- [ ] `docs/adr/ADR_019_HYBRID_FUNCTIONAL_OOP.md`
- [ ] `docs/guides/adding_triage_handler.md`
- [ ] `docs/guides/adding_classifier.md`
- [ ] `docs/guides/multi_tag_system.md`

### Phase 4: Multi-Tag TUI
- [ ] `docs/tui_mockups/multi_tag_rendering.md`
- [ ] `src/variance/tui/tag_renderer.py`
- [ ] Modified `src/variance/tui_renderer.py`
- [ ] `config/trading_rules.json` with `triage_display` section
- [ ] Updated README with screenshots

### Phase 5: Performance (Conditional)
- [ ] `docs/performance/screening_profile_baseline.md`
- [ ] Optimizations applied (if needed)
- [ ] <2s runtime for 100 tickers (if needed)

---

## Acceptance Criteria

### Phase 1: Type Safety
- ✅ `mypy --strict src/variance` produces zero errors
- ✅ CI fails on type errors
- ✅ All function signatures fully annotated

### Phase 2: Test Coverage
- ✅ `pytest --cov` shows 80%+ coverage
- ✅ All tests pass
- ✅ Coverage measured in CI

### Phase 3: Documentation
- ✅ All 4 documentation files complete
- ✅ Code examples tested and working
- ✅ ADR explains architectural rationale

### Phase 4: Multi-Tag TUI
- ✅ TUI displays primary + secondary tags
- ✅ Color-coded badges render correctly
- ✅ Configurable via JSON config
- ✅ Works in 80-column terminal

### Phase 5: Performance
- ✅ Profiling report complete
- ✅ Decision documented (optimize or skip)
- ✅ If optimized: <2s for 100 tickers

---

## Dependencies & Prerequisites

### Required Software
- Python 3.10+
- pip packages: `pytest`, `pytest-cov`, `mypy`, `rich`, `yfinance`
- Git (for version control)

### Required Access
- Read/write access to repository
- CI/CD pipeline configuration access (for mypy/coverage)
- Config file modification rights

### External Dependencies
- yfinance API (for market data fetching)
- Internet connection (for testing with real data)

---

## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Type errors in complex modules | High | Medium | Gradual migration, allow `# type: ignore` temporarily |
| Test coverage difficult to achieve | Medium | Low | Focus on business logic, skip simple getters/setters |
| TUI rendering breaks in some terminals | Medium | Low | Provide fallback mode (no emojis, basic colors) |
| Performance optimization not needed | High | Low | Make Phase 5 conditional on profiling |
| Configuration schema changes break existing setups | Low | Medium | Provide migration script, maintain backward compat |

---

## Success Metrics

| Metric | Baseline | Target | How to Measure |
|--------|----------|--------|----------------|
| **Type Safety** | Unknown | 100% | `mypy --strict` exit code 0 |
| **Test Coverage** | ~20% | 80%+ | `pytest --cov --cov-report=term` |
| **Documentation** | RFCs only | 4+ guides | File count in `docs/guides/` |
| **Multi-Tag Display** | No | Yes | TUI renders multiple tags |
| **Performance** | Unknown | <2s/100 | `time python -m variance.screen --limit 100` |

---

## Contact & Support

### Questions During Implementation
- Technical questions: [Contact]
- Architectural clarifications: Review RFCs 016-018
- Testing issues: See `tests/` for examples

### Deliverables Submission
- Submit PRs to: [Branch]
- Code review by: [Reviewer]
- Merge approval: [Approver]

---

## Appendix

### A. Useful Commands

```bash
# Type checking
mypy --strict src/variance

# Run tests with coverage
pytest --cov=src/variance --cov-report=html --cov-report=term-missing

# Profile screening
python -m cProfile -o screening.prof -m variance.screen --limit 100

# Lint code
ruff check . --fix
ruff format .

# Generate coverage report
coverage html
open htmlcov/index.html
```

### B. File Locations Quick Reference

```
variance-yfinance/
├── src/variance/
│   ├── triage/
│   │   ├── handlers/          # 9 handler files
│   │   ├── handler.py         # ABC
│   │   ├── chain.py           # Orchestrator
│   │   └── request.py         # Data classes
│   ├── classification/
│   │   ├── classifiers/       # 10 classifier files
│   │   ├── base.py            # ABC
│   │   └── registry.py        # Orchestrator
│   ├── screening/
│   │   ├── pipeline.py        # Template Method
│   │   └── enrichment/        # Strategy classes
│   └── tui/
│       └── tag_renderer.py    # NEW (Phase 4)
├── tests/
│   ├── triage/
│   │   └── handlers/          # NEW (Phase 2)
│   └── classification/
│       └── classifiers/       # NEW (Phase 2)
├── docs/
│   ├── adr/
│   │   └── ADR_019_*.md       # NEW (Phase 3)
│   ├── guides/
│   │   ├── adding_triage_handler.md    # NEW
│   │   ├── adding_classifier.md        # NEW
│   │   └── multi_tag_system.md         # NEW
│   └── performance/
│       └── screening_profile_baseline.md # NEW (Phase 5)
└── config/
    └── trading_rules.json     # Modified (Phase 4)
```

### C. References

- [Python Type Hints (PEP 484)](https://peps.python.org/pep-0484/)
- [mypy Documentation](https://mypy.readthedocs.io/)
- [pytest Documentation](https://docs.pytest.org/)
- [Rich Terminal Library](https://rich.readthedocs.io/)
- RFC_016: Chain of Responsibility for Triage
- RFC_017: Template Method for Screening
- RFC_018: Registry Pattern for Classification

---

**Document Version:** 1.0
**Last Updated:** 2025-12-23
**Status:** Ready for Contractor Handoff
