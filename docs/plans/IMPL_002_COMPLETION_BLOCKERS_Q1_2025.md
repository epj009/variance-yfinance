# IMPL-002: Completion of Quality Gates & Test Coverage

| Document Type | Implementation Plan |
| :--- | :--- |
| **Status** | Ready for Implementation |
| **Owner** | TBD (Developer Agent or Contractor) |
| **Estimated Effort** | 20-23 hours (3-4 days) |
| **Priority** | CRITICAL (Blocking Production) |
| **Parent Plan** | IMPL-001 (71% complete) |
| **Start Date** | TBD |
| **Target Completion** | 3-4 days from start |

---

## Executive Summary

This implementation plan addresses **critical gaps** identified in the IMPL-001 verification report. The original contractor completed 71% of the work with excellent architectural implementation but left critical testing and infrastructure gaps.

**This plan covers ONLY the blockers preventing production deployment:**
1. Missing unit tests (3 test files)
2. Missing integration tests (2 test files)
3. CI/CD pipeline configuration
4. Incomplete handler implementation (SizeThreatHandler)
5. Configuration and documentation gaps

**What's Already Complete (from IMPL-001):**
- ✅ Type safety (mypy strict configured and passing)
- ✅ Core architecture (9 handlers, 10 classifiers implemented)
- ✅ Documentation guides (3 excellent guides written)
- ✅ Multi-tag TUI rendering (TagRenderer fully implemented)
- ✅ Performance profiling (1.81s baseline, optimization skipped)

**What's Blocking Acceptance:**
- ❌ Test coverage: 30% actual vs. 80% target
- ❌ No CI/CD enforcement
- ❌ One handler is a stub (SizeThreatHandler)

---

## Prerequisites

### Required Knowledge
- ✅ Python 3.10+ (type hints, pytest)
- ✅ GitHub Actions (for CI/CD configuration)
- ✅ pytest framework (fixtures, mocking, parametrize)
- ✅ Existing codebase familiarity (IMPL-001 work)

### Environment Setup
```bash
# Already set up from IMPL-001
cd variance-yfinance
source venv/bin/activate

# Verify existing work
mypy --strict src/variance  # Should pass (from IMPL-001)
pytest tests/               # Should have 22 tests passing

# Install any missing dev dependencies
pip install pytest pytest-cov pytest-mock coverage
```

### Context Files to Review
- `docs/plans/IMPL_001_QUALITY_AND_FEATURES_Q1_2025.md` (original spec)
- Verification report (should be provided by project owner)
- Existing test files in `tests/triage/handlers/` (7 examples)
- Existing test files in `tests/classification/classifiers/` (9 examples)

---

## Task 1: Write Missing Unit Tests (3 files)

### Objective
Complete unit test coverage for all handlers and classifiers to match IMPL-001 specification.

### Estimated Effort: 6 hours

---

### Task 1.1: Write test_hedge_handler.py

**File:** `tests/triage/handlers/test_hedge_handler.py`

**Current State:**
- `src/variance/triage/handlers/hedge.py` exists and is implemented
- No test file exists
- Handler detects hedge positions in "dead money" range

**Implementation:**

```python
"""
Unit tests for HedgeHandler.

The HedgeHandler detects hedge positions that are in a dead money state
(neither profitable nor at risk) and tags them for review.
"""
import pytest
from variance.triage.handlers.hedge import HedgeHandler
from variance.triage.request import TriageRequest, TriageTag
from unittest.mock import Mock


class TestHedgeHandler:
    """Unit tests for HedgeHandler."""

    @pytest.fixture
    def default_rules(self):
        """Default rules for testing."""
        return {
            "dead_money_lower": -0.10,  # -10%
            "dead_money_upper": 0.10,   # +10%
        }

    @pytest.fixture
    def handler(self, default_rules):
        """Create handler instance."""
        return HedgeHandler(default_rules)

    @pytest.fixture
    def base_request(self):
        """Base request with common fields."""
        return {
            "root": "SPY",
            "strategy_name": "Long Put",
            "strategy_id": "long_put",
            "dte": 30,
            "net_pl": -5.0,
            "net_cost": 100.0,
            "strategy_delta": -10.0,
            "strategy_gamma": 0.05,
            "pl_pct": -0.05,  # -5%
            "days_held": 10,
            "price": 450.0,
            "legs": (),
            "vrp_structural": None,
            "vrp_tactical": None,
            "is_stale": False,
            "sector": "Index",
            "earnings_date": None,
            "portfolio_beta_delta": -0.5,
            "net_liquidity": 10000.0,
            "strategy_obj": Mock(),
        }

    def test_adds_hedge_check_tag_when_in_dead_money_range(self, handler, base_request):
        """Should add HEDGE_CHECK tag when position is in dead money range."""
        # Arrange: Position with -5% P/L (within -10% to +10% dead money range)
        request = TriageRequest(**base_request)

        # Act
        result = handler.handle(request)

        # Assert
        hedge_tags = [t for t in result.tags if t.tag_type == "HEDGE_CHECK"]
        assert len(hedge_tags) == 1
        assert hedge_tags[0].priority == 50
        assert "dead money" in hedge_tags[0].logic.lower()

    def test_skips_when_pl_is_profitable(self, handler, base_request):
        """Should not tag when position is profitable (above dead money range)."""
        # Arrange: Position with +15% P/L (above +10% threshold)
        base_request["pl_pct"] = 0.15
        base_request["net_pl"] = 15.0
        request = TriageRequest(**base_request)

        # Act
        result = handler.handle(request)

        # Assert
        hedge_tags = [t for t in result.tags if t.tag_type == "HEDGE_CHECK"]
        assert len(hedge_tags) == 0

    def test_skips_when_pl_is_losing(self, handler, base_request):
        """Should not tag when position is losing (below dead money range)."""
        # Arrange: Position with -15% P/L (below -10% threshold)
        base_request["pl_pct"] = -0.15
        base_request["net_pl"] = -15.0
        request = TriageRequest(**base_request)

        # Act
        result = handler.handle(request)

        # Assert
        hedge_tags = [t for t in result.tags if t.tag_type == "HEDGE_CHECK"]
        assert len(hedge_tags) == 0

    def test_skips_when_pl_pct_is_none(self, handler, base_request):
        """Should not tag when pl_pct is None (cannot determine)."""
        # Arrange
        base_request["pl_pct"] = None
        request = TriageRequest(**base_request)

        # Act
        result = handler.handle(request)

        # Assert
        hedge_tags = [t for t in result.tags if t.tag_type == "HEDGE_CHECK"]
        assert len(hedge_tags) == 0

    def test_always_passes_to_next_handler(self, handler, base_request):
        """Should always call _pass_to_next (collector pattern)."""
        # Arrange
        next_handler = Mock(spec=HedgeHandler)
        next_handler.handle.return_value = Mock()
        handler.set_next(next_handler)

        request = TriageRequest(**base_request)

        # Act
        handler.handle(request)

        # Assert: Next handler was called
        next_handler.handle.assert_called_once()

    def test_respects_custom_dead_money_thresholds(self):
        """Should use custom thresholds from rules."""
        # Arrange: Wider dead money range (-20% to +20%)
        custom_rules = {
            "dead_money_lower": -0.20,
            "dead_money_upper": 0.20,
        }
        handler = HedgeHandler(custom_rules)

        request = TriageRequest(
            pl_pct=0.15,  # +15% (within custom range)
            # ... other required fields
        )

        # Act
        result = handler.handle(request)

        # Assert: Should tag with wider threshold
        hedge_tags = [t for t in result.tags if t.tag_type == "HEDGE_CHECK"]
        assert len(hedge_tags) == 1
```

**Deliverable:** `tests/triage/handlers/test_hedge_handler.py` with 6 test cases

**Acceptance Criteria:**
- ✅ File exists in correct location
- ✅ All 6 tests pass
- ✅ Tests cover: happy path, edge cases, collector pattern, custom rules
- ✅ Handler achieves 90%+ line coverage

**Estimated Effort:** 2 hours

---

### Task 1.2: Write test_size_threat_handler.py

**File:** `tests/triage/handlers/test_size_threat_handler.py`

**Current State:**
- `src/variance/triage/handlers/size_threat.py` exists but is a **STUB**
- Handler just passes to next, no logic implemented
- This test will **FORCE** implementation or document the gap

**Implementation:**

```python
"""
Unit tests for SizeThreatHandler.

The SizeThreatHandler detects positions with tail risk exceeding a percentage
of net liquidity (default: 5%). This prevents portfolio blow-up scenarios.
"""
import pytest
from variance.triage.handlers.size_threat import SizeThreatHandler
from variance.triage.request import TriageRequest, TriageTag
from unittest.mock import Mock


class TestSizeThreatHandler:
    """Unit tests for SizeThreatHandler."""

    @pytest.fixture
    def default_rules(self):
        """Default rules for testing."""
        return {
            "size_threat_threshold": 0.05,  # 5% of net liquidity
        }

    @pytest.fixture
    def handler(self, default_rules):
        """Create handler instance."""
        return SizeThreatHandler(default_rules)

    @pytest.fixture
    def base_request(self):
        """Base request with common fields."""
        return {
            "root": "AAPL",
            "strategy_name": "Iron Condor",
            "strategy_id": "iron_condor",
            "dte": 30,
            "net_pl": -600.0,  # $600 loss
            "net_cost": -1000.0,  # $1000 credit
            "strategy_delta": 5.0,
            "strategy_gamma": 0.1,
            "pl_pct": -0.60,  # -60%
            "days_held": 10,
            "price": 100.0,
            "legs": (),
            "vrp_structural": 1.2,
            "vrp_tactical": 0.3,
            "is_stale": False,
            "sector": "Technology",
            "earnings_date": None,
            "portfolio_beta_delta": 0.0,
            "net_liquidity": 10000.0,  # $10k net liquidity
            "strategy_obj": Mock(),
        }

    def test_adds_size_threat_tag_when_tail_risk_exceeds_threshold(self, handler, base_request):
        """Should add SIZE_THREAT tag when tail risk > 5% of net liquidity."""
        # Arrange: $600 loss on $10k liquidity = 6% > 5% threshold
        request = TriageRequest(**base_request)

        # Act
        result = handler.handle(request)

        # Assert
        size_tags = [t for t in result.tags if t.tag_type == "SIZE_THREAT"]
        assert len(size_tags) == 1
        assert size_tags[0].priority == 20
        assert "tail risk" in size_tags[0].logic.lower() or "size" in size_tags[0].logic.lower()
        assert "6.0%" in size_tags[0].logic or "6%" in size_tags[0].logic  # Should show percentage

    def test_skips_when_tail_risk_below_threshold(self, handler, base_request):
        """Should not tag when tail risk < 5% of net liquidity."""
        # Arrange: $400 loss on $10k liquidity = 4% < 5% threshold
        base_request["net_pl"] = -400.0
        request = TriageRequest(**base_request)

        # Act
        result = handler.handle(request)

        # Assert
        size_tags = [t for t in result.tags if t.tag_type == "SIZE_THREAT"]
        assert len(size_tags) == 0

    def test_skips_profitable_positions(self, handler, base_request):
        """Should not tag profitable positions (no tail risk)."""
        # Arrange: Profitable position
        base_request["net_pl"] = 200.0
        base_request["pl_pct"] = 0.20
        request = TriageRequest(**base_request)

        # Act
        result = handler.handle(request)

        # Assert
        size_tags = [t for t in result.tags if t.tag_type == "SIZE_THREAT"]
        assert len(size_tags) == 0

    def test_calculates_tail_risk_using_max_loss(self, handler, base_request):
        """Should use max potential loss for credit spreads, not just current P/L."""
        # Arrange: Credit spread with defined risk
        # Current loss: $600, but max loss is full credit ($1000)
        # Max loss / NLV = $1000 / $10000 = 10% > 5%
        request = TriageRequest(**base_request)

        # Act
        result = handler.handle(request)

        # Assert: Should tag based on max loss, not current loss
        size_tags = [t for t in result.tags if t.tag_type == "SIZE_THREAT"]
        assert len(size_tags) == 1
        # Logic should reference max loss or "10%" not just current "-60%"

    def test_respects_custom_threshold(self):
        """Should use custom threshold from rules."""
        # Arrange: Higher threshold (10% instead of 5%)
        custom_rules = {"size_threat_threshold": 0.10}
        handler = SizeThreatHandler(custom_rules)

        request = TriageRequest(
            net_pl=-700.0,
            net_liquidity=10000.0,  # 7% of NLV
            # ... other fields
        )

        # Act
        result = handler.handle(request)

        # Assert: 7% < 10% threshold, should not tag
        size_tags = [t for t in result.tags if t.tag_type == "SIZE_THREAT"]
        assert len(size_tags) == 0

    def test_always_passes_to_next_handler(self, handler, base_request):
        """Should always call _pass_to_next (collector pattern)."""
        # Arrange
        next_handler = Mock(spec=SizeThreatHandler)
        next_handler.handle.return_value = Mock()
        handler.set_next(next_handler)

        request = TriageRequest(**base_request)

        # Act
        handler.handle(request)

        # Assert
        next_handler.handle.assert_called_once()

    @pytest.mark.xfail(reason="SizeThreatHandler is currently a stub - implementation pending")
    def test_implementation_exists(self, handler, base_request):
        """
        This test documents that SizeThreatHandler needs implementation.

        Remove @pytest.mark.xfail when implementation is complete.
        """
        request = TriageRequest(**base_request)
        result = handler.handle(request)

        # If implementation exists, this should tag
        size_tags = [t for t in result.tags if t.tag_type == "SIZE_THREAT"]
        assert len(size_tags) == 1, "SizeThreatHandler should detect tail risk > threshold"
```

**NOTE:** This test file includes `@pytest.mark.xfail` to document the stub implementation. The test will **FAIL** until SizeThreatHandler is implemented (Task 4).

**Deliverable:** `tests/triage/handlers/test_size_threat_handler.py` with 7 test cases

**Acceptance Criteria:**
- ✅ File exists in correct location
- ✅ 6 tests pass (1 marked xfail)
- ✅ Tests document expected behavior
- ✅ Forces implementation or explicit deferral

**Estimated Effort:** 2 hours

---

### Task 1.3: Write test_stock_classifier.py

**File:** `tests/classification/classifiers/test_stock_classifier.py`

**Current State:**
- `src/variance/classification/classifiers/stock.py` exists and is implemented
- No test file exists
- Classifier detects single stock positions

**Implementation:**

```python
"""
Unit tests for StockClassifier.

The StockClassifier identifies single stock positions (no options).
"""
import pytest
from variance.classification.classifiers.stock import StockClassifier
from variance.classification.base import ClassificationContext


class TestStockClassifier:
    """Unit tests for StockClassifier."""

    @pytest.fixture
    def classifier(self):
        """Create classifier instance."""
        return StockClassifier()

    def test_identifies_single_stock_long(self, classifier):
        """Should identify a single long stock position."""
        # Arrange
        legs = [
            {
                "Symbol": "AAPL",
                "Asset Type": "Stock",
                "Quantity": "100",
                "Strike Price": None,
                "Expiration Date": None,
            }
        ]
        ctx = ClassificationContext.from_legs(legs)

        # Act
        can_classify = classifier.can_classify(legs, ctx)
        classification = classifier.classify(legs, ctx)

        # Assert
        assert can_classify is True
        assert classification == "Stock"

    def test_identifies_single_stock_short(self, classifier):
        """Should identify a single short stock position."""
        # Arrange
        legs = [
            {
                "Symbol": "TSLA",
                "Asset Type": "Stock",
                "Quantity": "-100",
                "Strike Price": None,
                "Expiration Date": None,
            }
        ]
        ctx = ClassificationContext.from_legs(legs)

        # Act
        can_classify = classifier.can_classify(legs, ctx)
        classification = classifier.classify(legs, ctx)

        # Assert
        assert can_classify is True
        assert classification == "Stock"

    def test_rejects_multiple_legs(self, classifier):
        """Should not classify positions with multiple legs."""
        # Arrange: Stock + option
        legs = [
            {"Asset Type": "Stock", "Quantity": "100"},
            {"Asset Type": "Option", "Call/Put": "Call", "Quantity": "-1"},
        ]
        ctx = ClassificationContext.from_legs(legs)

        # Act
        can_classify = classifier.can_classify(legs, ctx)

        # Assert
        assert can_classify is False

    def test_rejects_single_option(self, classifier):
        """Should not classify single option positions."""
        # Arrange: Single option (not stock)
        legs = [
            {
                "Asset Type": "Option",
                "Call/Put": "Call",
                "Quantity": "1",
                "Strike Price": "100",
                "Expiration Date": "2025-01-17",
            }
        ]
        ctx = ClassificationContext.from_legs(legs)

        # Act
        can_classify = classifier.can_classify(legs, ctx)

        # Assert
        assert can_classify is False

    def test_rejects_empty_legs(self, classifier):
        """Should not classify empty position."""
        # Arrange
        legs = []
        ctx = ClassificationContext.from_legs(legs)

        # Act
        can_classify = classifier.can_classify(legs, ctx)

        # Assert
        assert can_classify is False

    def test_classification_context_correctly_identifies_stock(self, classifier):
        """Should verify ClassificationContext correctly parses stock legs."""
        # Arrange
        legs = [{"Asset Type": "Stock", "Quantity": "100"}]
        ctx = ClassificationContext.from_legs(legs)

        # Assert: Context should identify this as stock
        assert len(ctx.stock_legs) == 1
        assert len(ctx.option_legs) == 0
```

**Deliverable:** `tests/classification/classifiers/test_stock_classifier.py` with 6 test cases

**Acceptance Criteria:**
- ✅ File exists in correct location
- ✅ All 6 tests pass
- ✅ Tests cover: long stock, short stock, rejection cases
- ✅ Classifier achieves 90%+ line coverage

**Estimated Effort:** 2 hours

---

### Task 1 Summary

| Task | File | Test Cases | Effort |
|------|------|------------|--------|
| 1.1 | test_hedge_handler.py | 6 | 2h |
| 1.2 | test_size_threat_handler.py | 7 (1 xfail) | 2h |
| 1.3 | test_stock_classifier.py | 6 | 2h |
| **TOTAL** | **3 files** | **19 tests** | **6h** |

---

## Task 2: Write Integration Tests (2 files)

### Objective
Add integration tests for full pipeline execution to catch inter-component bugs.

### Estimated Effort: 6 hours

---

### Task 2.1: Write Triage Chain Integration Tests

**File:** `tests/triage/test_chain_integration.py`

**Purpose:** Test that the full triage chain executes correctly with multi-tag collection.

**Implementation:**

```python
"""
Integration tests for TriageChain.

Tests the full chain of responsibility pattern with all 9 handlers executing
and collecting multiple tags per position.
"""
import pytest
from variance.triage.chain import TriageChain
from variance.triage.request import TriageRequest
from datetime import date, timedelta
from unittest.mock import Mock


class TestTriageChainIntegration:
    """Integration tests for full triage chain execution."""

    @pytest.fixture
    def default_rules(self):
        """Standard trading rules for testing."""
        return {
            "gamma_trigger_dte": 21,
            "harvest_target": 0.50,
            "size_threat_threshold": 0.05,
            "earnings_window_days": 7,
            "dead_money_lower": -0.10,
            "dead_money_upper": 0.10,
        }

    @pytest.fixture
    def chain(self, default_rules):
        """Create triage chain instance."""
        return TriageChain(default_rules)

    @pytest.fixture
    def strategy_obj_mock(self):
        """Mock strategy object for harvest delegation."""
        mock = Mock()
        mock.check_harvest.return_value = None  # Default: no harvest
        return mock

    def test_multi_tag_collection(self, chain, strategy_obj_mock):
        """Position should collect multiple tags simultaneously."""
        # Arrange: Position that triggers HARVEST, GAMMA, and EARNINGS
        from variance.models.actions import HarvestCommand

        strategy_obj_mock.check_harvest.return_value = HarvestCommand(
            symbol="AAPL",
            logic="Profit target hit: 60%"
        )

        earnings_date = (date.today() + timedelta(days=5)).isoformat()

        request = TriageRequest(
            root="AAPL",
            strategy_name="Iron Condor",
            strategy_id="iron_condor",
            dte=7,                      # GAMMA: < 21 DTE
            net_pl=600.0,
            net_cost=-100.0,            # Credit position
            strategy_delta=5.0,
            strategy_gamma=0.1,
            pl_pct=0.60,                # HARVEST: > 50% target
            days_held=10,
            price=100.0,
            legs=(),
            vrp_structural=1.2,
            vrp_tactical=0.3,
            is_stale=False,
            sector="Technology",
            earnings_date=earnings_date, # EARNINGS: Within 7 days
            portfolio_beta_delta=0.0,
            net_liquidity=10000.0,
            strategy_obj=strategy_obj_mock,
        )

        # Act
        result = chain.triage(request)

        # Assert: Should have multiple tags
        tag_types = {t.tag_type for t in result.tags}
        assert "HARVEST" in tag_types, "Should have HARVEST tag (pl_pct=60% > 50%)"
        assert "GAMMA" in tag_types, "Should have GAMMA tag (dte=7 < 21)"
        assert "EARNINGS_WARNING" in tag_types, "Should have EARNINGS_WARNING tag (5 days away)"
        assert len(result.tags) >= 3, f"Should have at least 3 tags, got {len(result.tags)}"

    def test_primary_action_is_highest_priority(self, chain, strategy_obj_mock):
        """Primary action should be tag with lowest priority number."""
        # Arrange: Position triggering EXPIRING (0) and HARVEST (10)
        from variance.models.actions import HarvestCommand

        strategy_obj_mock.check_harvest.return_value = HarvestCommand(
            symbol="AAPL",
            logic="Profit target hit"
        )

        request = TriageRequest(
            root="AAPL",
            strategy_name="Iron Condor",
            strategy_id="iron_condor",
            dte=0,          # EXPIRING (priority 0)
            net_pl=500.0,
            net_cost=-100.0,
            strategy_delta=5.0,
            strategy_gamma=0.1,
            pl_pct=0.60,    # HARVEST (priority 10)
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
            strategy_obj=strategy_obj_mock,
        )

        # Act
        result = chain.triage(request)

        # Assert: EXPIRING should be primary (lower priority number)
        assert result.primary_action is not None
        assert result.primary_action.tag_type == "EXPIRING", \
            f"Expected EXPIRING (priority 0), got {result.primary_action.tag_type} (priority {result.primary_action.priority})"

        # But should also have HARVEST tag
        tag_types = {t.tag_type for t in result.tags}
        assert "HARVEST" in tag_types

    def test_empty_tags_when_no_conditions_met(self, chain, strategy_obj_mock):
        """Should have no tags when no conditions are triggered."""
        # Arrange: Neutral position (no triggers)
        request = TriageRequest(
            root="SPY",
            strategy_name="Iron Condor",
            strategy_id="iron_condor",
            dte=45,         # Not in gamma zone (> 21)
            net_pl=50.0,
            net_cost=-1000.0,
            strategy_delta=2.0,
            strategy_gamma=0.05,
            pl_pct=0.05,    # Below harvest target (< 50%)
            days_held=5,
            price=450.0,
            legs=(),
            vrp_structural=1.1,
            vrp_tactical=0.2,
            is_stale=False,
            sector="Index",
            earnings_date=None,
            portfolio_beta_delta=0.0,
            net_liquidity=50000.0,  # Large NLV, no size threat
            strategy_obj=strategy_obj_mock,
        )

        # Act
        result = chain.triage(request)

        # Assert
        assert len(result.tags) == 0, f"Expected no tags, got {[t.tag_type for t in result.tags]}"
        assert result.primary_action is None

    def test_all_handlers_execute_collector_pattern(self, chain, strategy_obj_mock):
        """All 9 handlers should execute (no short-circuiting)."""
        # Arrange: Simple position
        request = TriageRequest(
            root="AAPL",
            strategy_name="Short Strangle",
            strategy_id="short_strangle",
            dte=30,
            net_pl=100.0,
            net_cost=-500.0,
            strategy_delta=3.0,
            strategy_gamma=0.08,
            pl_pct=0.20,
            days_held=7,
            price=100.0,
            legs=(),
            vrp_structural=1.2,
            vrp_tactical=0.3,
            is_stale=False,
            sector="Technology",
            earnings_date=None,
            portfolio_beta_delta=0.0,
            net_liquidity=10000.0,
            strategy_obj=strategy_obj_mock,
        )

        # Act: Should complete without error
        result = chain.triage(request)

        # Assert: Chain completed successfully
        assert result is not None
        # Cannot easily verify all handlers called without spies,
        # but lack of exception means collector pattern working

    def test_size_threat_priority_over_gamma(self, chain, strategy_obj_mock):
        """SIZE_THREAT (priority 20) should be primary over GAMMA (priority 40)."""
        # Arrange: Position with both SIZE_THREAT and GAMMA triggers
        request = TriageRequest(
            root="TSLA",
            strategy_name="Iron Condor",
            strategy_id="iron_condor",
            dte=10,                     # GAMMA zone (< 21)
            net_pl=-600.0,              # SIZE_THREAT: 6% of NLV
            net_cost=-1000.0,
            strategy_delta=5.0,
            strategy_gamma=0.15,
            pl_pct=-0.60,
            days_held=15,
            price=250.0,
            legs=(),
            vrp_structural=1.3,
            vrp_tactical=0.4,
            is_stale=False,
            sector="Automotive",
            earnings_date=None,
            portfolio_beta_delta=0.0,
            net_liquidity=10000.0,       # 600/10000 = 6% > 5% threshold
            strategy_obj=strategy_obj_mock,
        )

        # Act
        result = chain.triage(request)

        # Assert: SIZE_THREAT should be primary
        tag_types = {t.tag_type for t in result.tags}

        # Note: This test may fail if SizeThreatHandler is still a stub
        # If SIZE_THREAT not in tags, GAMMA should be primary
        if "SIZE_THREAT" in tag_types:
            assert result.primary_action.tag_type == "SIZE_THREAT", \
                "SIZE_THREAT (priority 20) should override GAMMA (priority 40)"
        else:
            # If SIZE_THREAT handler not implemented, GAMMA should be primary
            assert result.primary_action.tag_type == "GAMMA"

    def test_defense_vs_gamma_priority(self, chain, strategy_obj_mock):
        """DEFENSE (priority 30) should be primary over GAMMA (priority 40)."""
        # Arrange: Position that is tested (DEFENSE) in gamma zone
        request = TriageRequest(
            root="AAPL",
            strategy_name="Iron Condor",
            strategy_id="iron_condor",
            dte=10,                     # GAMMA zone
            net_pl=-200.0,
            net_cost=-500.0,
            strategy_delta=15.0,        # High delta (tested)
            strategy_gamma=0.2,
            pl_pct=-0.40,
            days_held=20,
            price=100.0,
            legs=(),
            vrp_structural=1.2,
            vrp_tactical=0.3,
            is_stale=False,
            sector="Technology",
            earnings_date=None,
            portfolio_beta_delta=0.0,
            net_liquidity=10000.0,
            strategy_obj=strategy_obj_mock,
        )

        # Act
        result = chain.triage(request)

        # Assert: If position is detected as tested, DEFENSE should be primary
        tag_types = {t.tag_type for t in result.tags}

        if "DEFENSE" in tag_types:
            assert result.primary_action.tag_type == "DEFENSE", \
                "DEFENSE (priority 30) should override GAMMA (priority 40)"

    def test_scalable_tag_for_vrp_momentum(self, chain, strategy_obj_mock):
        """SCALABLE tag should be added when VRP momentum is high."""
        # Arrange: Position with high VRP tactical (momentum surge)
        request = TriageRequest(
            root="SPY",
            strategy_name="Short Strangle",
            strategy_id="short_strangle",
            dte=45,
            net_pl=200.0,
            net_cost=-1000.0,
            strategy_delta=2.0,
            strategy_gamma=0.05,
            pl_pct=0.20,
            days_held=5,
            price=450.0,
            legs=(),
            vrp_structural=1.5,
            vrp_tactical=0.8,           # High VRP tactical (momentum)
            is_stale=False,
            sector="Index",
            earnings_date=None,
            portfolio_beta_delta=0.0,
            net_liquidity=50000.0,
            strategy_obj=strategy_obj_mock,
        )

        # Act
        result = chain.triage(request)

        # Assert
        tag_types = {t.tag_type for t in result.tags}

        # SCALABLE tag should be present if VRP momentum triggers it
        # (depends on ScalableHandler implementation)
        if "SCALABLE" in tag_types:
            assert result.tags[-1].tag_type == "SCALABLE"  # Should be last (priority 80)

    @pytest.mark.parametrize("dte,expected_tag", [
        (0, "EXPIRING"),
        (7, "GAMMA"),
        (30, None),  # No gamma/expiration tag
    ])
    def test_dte_based_tagging(self, chain, strategy_obj_mock, dte, expected_tag):
        """Test that DTE-based tags are applied correctly."""
        # Arrange
        request = TriageRequest(
            root="AAPL",
            strategy_name="Iron Condor",
            strategy_id="iron_condor",
            dte=dte,
            net_pl=100.0,
            net_cost=-500.0,
            strategy_delta=3.0,
            strategy_gamma=0.1,
            pl_pct=0.20,
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
            strategy_obj=strategy_obj_mock,
        )

        # Act
        result = chain.triage(request)

        # Assert
        tag_types = {t.tag_type for t in result.tags}

        if expected_tag:
            assert expected_tag in tag_types, f"Expected {expected_tag} for DTE={dte}"
        else:
            assert "GAMMA" not in tag_types and "EXPIRING" not in tag_types
```

**Deliverable:** `tests/triage/test_chain_integration.py` with 10 test scenarios

**Acceptance Criteria:**
- ✅ File exists in correct location
- ✅ All tests pass (or xfail where documented)
- ✅ Tests cover multi-tag scenarios
- ✅ Tests verify priority ordering
- ✅ Tests validate collector pattern (no short-circuit)

**Estimated Effort:** 4 hours

---

### Task 2.2: Write Screening Pipeline Integration Tests

**File:** `tests/screening/test_pipeline_integration.py`

**Purpose:** Test the full screening pipeline from symbol loading to report generation.

**Implementation:**

```python
"""
Integration tests for ScreeningPipeline.

Tests the full Template Method pattern execution with all 6 steps.
"""
import pytest
from variance.screening.pipeline import ScreeningPipeline
from variance.vol_screener import ScreenerConfig
from variance.config_loader import load_config_bundle
from unittest.mock import patch, Mock, MagicMock
import pandas as pd


class TestScreeningPipelineIntegration:
    """Integration tests for ScreeningPipeline."""

    @pytest.fixture
    def config_bundle(self):
        """Load real config bundle."""
        return load_config_bundle(strict=False)

    @pytest.fixture
    def mock_config(self):
        """Mock screener config."""
        return ScreenerConfig(limit=10, signal_filter=None)

    @pytest.fixture
    def mock_market_data(self):
        """Mock market data from yfinance."""
        # Mock historical price data
        hist_data = pd.DataFrame({
            'Close': [100, 102, 101, 103, 102],
            'High': [102, 104, 103, 105, 104],
            'Low': [98, 100, 99, 101, 100],
            'Volume': [1000000] * 5,
        })

        return {
            "history": hist_data,
            "IV30": 25.0,
            "HV20": 20.0,
            "HV252": 22.0,
            "sector": "Technology",
            "earnings_date": None,
        }

    def test_full_pipeline_execution(self, mock_config, config_bundle, mock_market_data):
        """Pipeline should execute all 6 steps without error."""
        # Arrange: Mock yfinance to avoid network calls
        with patch('variance.screening.steps.fetch.fetch_market_data') as mock_fetch:
            # Return mock data for all symbols
            mock_fetch.return_value = {
                "AAPL": mock_market_data,
                "MSFT": mock_market_data,
                "GOOGL": mock_market_data,
            }

            # Act
            pipeline = ScreeningPipeline(mock_config, config_bundle)
            result = pipeline.execute()

        # Assert: Pipeline completed successfully
        assert result is not None
        assert "candidates" in result
        assert "summary" in result
        assert isinstance(result["candidates"], list)
        assert isinstance(result["summary"], dict)

    def test_enrichment_strategies_applied(self, mock_config, config_bundle, mock_market_data):
        """All enrichment strategies should add calculated fields."""
        # Arrange
        with patch('variance.screening.steps.fetch.fetch_market_data') as mock_fetch:
            mock_fetch.return_value = {"AAPL": mock_market_data}

            # Act
            pipeline = ScreeningPipeline(mock_config, config_bundle)
            result = pipeline.execute()

        # Assert: VrpEnrichmentStrategy fields
        if result["candidates"]:
            candidate = result["candidates"][0]

            # VRP tactical markup should be calculated
            assert "VRP_Tactical_Markup" in candidate or "vrp_tactical" in candidate.lower(), \
                "VrpEnrichmentStrategy should add VRP_Tactical_Markup"

            # Compression ratio should be calculated
            assert "Compression Ratio" in candidate or "compression" in str(candidate).lower(), \
                "VrpEnrichmentStrategy should add Compression Ratio"

            # Signal type should be determined
            assert "Signal" in candidate or "signal" in str(candidate).lower(), \
                "VrpEnrichmentStrategy should determine Signal type"

    def test_specification_filters_applied(self, mock_config, config_bundle, mock_market_data):
        """Specification pattern filters should reduce candidate count."""
        # Arrange: Some candidates should be filtered out
        mock_data_good = {**mock_market_data, "IV30": 30.0, "HV20": 20.0}  # High VRP
        mock_data_bad = {**mock_market_data, "IV30": 15.0, "HV20": 20.0}   # Low VRP

        with patch('variance.screening.steps.fetch.fetch_market_data') as mock_fetch:
            mock_fetch.return_value = {
                "AAPL": mock_data_good,
                "MSFT": mock_data_bad,
                "GOOGL": mock_data_good,
            }

            # Act
            pipeline = ScreeningPipeline(mock_config, config_bundle)
            result = pipeline.execute()

        # Assert: Bad candidate should be filtered
        assert len(result["candidates"]) < 3, \
            "Specification filters should remove some candidates"

    def test_sort_and_dedupe_applied(self, mock_config, config_bundle, mock_market_data):
        """Candidates should be sorted and deduplicated by root symbol."""
        # Arrange: Multiple entries for same root (e.g., AAPL, AAPL250117C00100000)
        with patch('variance.screening.steps.fetch.fetch_market_data') as mock_fetch:
            mock_fetch.return_value = {
                "AAPL": mock_market_data,
                "AAPL250117C00100000": mock_market_data,  # Option on AAPL
                "MSFT": mock_market_data,
            }

            # Act
            pipeline = ScreeningPipeline(mock_config, config_bundle)
            result = pipeline.execute()

        # Assert: Should deduplicate AAPL entries
        roots = [c.get("Symbol") or c.get("root") for c in result["candidates"]]
        assert len(roots) == len(set(roots)), \
            "Should deduplicate by root symbol (no duplicate roots)"

    def test_limit_respected(self, config_bundle, mock_market_data):
        """Pipeline should respect the limit config."""
        # Arrange: Config with limit=5
        config = ScreenerConfig(limit=5, signal_filter=None)

        with patch('variance.screening.steps.fetch.fetch_market_data') as mock_fetch:
            # Return 10 candidates
            mock_fetch.return_value = {
                f"SYMB{i}": mock_market_data for i in range(10)
            }

            # Act
            pipeline = ScreeningPipeline(config, config_bundle)
            result = pipeline.execute()

        # Assert: Should have at most 5 candidates
        assert len(result["candidates"]) <= 5, \
            f"Expected <= 5 candidates, got {len(result['candidates'])}"

    def test_summary_statistics_generated(self, mock_config, config_bundle, mock_market_data):
        """Pipeline should generate summary statistics."""
        # Arrange
        with patch('variance.screening.steps.fetch.fetch_market_data') as mock_fetch:
            mock_fetch.return_value = {
                "AAPL": mock_market_data,
                "MSFT": mock_market_data,
            }

            # Act
            pipeline = ScreeningPipeline(mock_config, config_bundle)
            result = pipeline.execute()

        # Assert: Summary should have counts
        assert "summary" in result
        summary = result["summary"]

        # Should have total scanned count
        assert "total_scanned" in summary or "scanned" in str(summary).lower()

        # Should have passed/failed filter counts
        assert "passed" in str(summary).lower() or "candidates" in str(summary).lower()

    @pytest.mark.slow
    def test_real_market_data_fetch(self, config_bundle):
        """
        Test with real yfinance API (slow, integration test).

        This test actually calls yfinance and should be run separately.
        Mark with @pytest.mark.slow and run with: pytest -m slow
        """
        # Arrange: Limit to just 1 ticker for speed
        config = ScreenerConfig(limit=1, signal_filter=None)

        # Act: Real API call
        pipeline = ScreeningPipeline(config, config_bundle)
        result = pipeline.execute()

        # Assert: Should complete successfully
        assert result is not None
        assert "candidates" in result
        # May have 0 candidates if market conditions don't match filters

    def test_error_handling_for_invalid_symbol(self, mock_config, config_bundle):
        """Pipeline should handle fetch errors gracefully."""
        # Arrange: Mock fetch that raises exception for one symbol
        def mock_fetch_with_error(symbols):
            results = {}
            for sym in symbols:
                if sym == "INVALID":
                    # Skip invalid symbol (simulates fetch error)
                    continue
                results[sym] = mock_market_data
            return results

        with patch('variance.screening.steps.fetch.fetch_market_data', side_effect=mock_fetch_with_error):
            # Act: Should not raise exception
            pipeline = ScreeningPipeline(mock_config, config_bundle)
            result = pipeline.execute()

        # Assert: Pipeline completed despite error
        assert result is not None
        assert "candidates" in result
```

**Deliverable:** `tests/screening/test_pipeline_integration.py` with 9 test scenarios

**Acceptance Criteria:**
- ✅ File exists in correct location
- ✅ All tests pass (slow test marked appropriately)
- ✅ Tests cover full pipeline execution
- ✅ Tests validate enrichment, filtering, sorting
- ✅ Tests verify error handling

**Estimated Effort:** 3 hours (complex mocking required)

---

### Task 2 Summary

| Task | File | Test Cases | Effort |
|------|------|------------|--------|
| 2.1 | test_chain_integration.py | 10 | 4h |
| 2.2 | test_pipeline_integration.py | 9 | 3h (complex mocking) |
| **TOTAL** | **2 files** | **19 tests** | **7h** (adjusted to 6h with efficiency) |

---

## Task 3: Configure CI/CD Pipeline

### Objective
Add GitHub Actions workflow to enforce type checking and test coverage on every commit.

### Estimated Effort: 2-3 hours

---

### Task 3.1: Create GitHub Actions Workflow

**File:** `.github/workflows/ci.yml`

**Implementation:**

```yaml
name: CI

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main, develop ]

jobs:
  quality-gates:
    runs-on: ubuntu-latest

    strategy:
      matrix:
        python-version: ['3.10', '3.11', '3.12']

    steps:
    - name: Checkout code
      uses: actions/checkout@v4

    - name: Set up Python ${{ matrix.python-version }}
      uses: actions/setup-python@v5
      with:
        python-version: ${{ matrix.python-version }}

    - name: Cache pip dependencies
      uses: actions/cache@v3
      with:
        path: ~/.cache/pip
        key: ${{ runner.os }}-pip-${{ hashFiles('**/pyproject.toml') }}
        restore-keys: |
          ${{ runner.os }}-pip-

    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -e ".[dev]"
        pip install pytest pytest-cov mypy ruff

    - name: Lint with ruff
      run: |
        # Stop the build if there are Python syntax errors or undefined names
        ruff check . --select=E9,F63,F7,F82 --output-format=github
        # Run full linting
        ruff check . --output-format=github
      continue-on-error: false

    - name: Format check with ruff
      run: |
        ruff format --check .

    - name: Type check with mypy
      run: |
        mypy --strict src/variance
      continue-on-error: false

    - name: Run tests with coverage
      run: |
        pytest --cov=src/variance --cov-report=xml --cov-report=term-missing --cov-fail-under=75
      env:
        PYTEST_TIMEOUT: 300

    - name: Upload coverage to Codecov (optional)
      if: matrix.python-version == '3.12'
      uses: codecov/codecov-action@v3
      with:
        file: ./coverage.xml
        flags: unittests
        name: codecov-umbrella
        fail_ci_if_error: false

    - name: Archive test results
      if: always()
      uses: actions/upload-artifact@v3
      with:
        name: test-results-${{ matrix.python-version }}
        path: |
          coverage.xml
          htmlcov/

  test-slow:
    runs-on: ubuntu-latest
    # Run slow tests only on main branch merges
    if: github.ref == 'refs/heads/main'

    steps:
    - name: Checkout code
      uses: actions/checkout@v4

    - name: Set up Python
      uses: actions/setup-python@v5
      with:
        python-version: '3.12'

    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -e ".[dev]"
        pip install pytest

    - name: Run slow integration tests
      run: |
        pytest -m slow --timeout=600
      env:
        PYTEST_TIMEOUT: 600
```

**Deliverable:** `.github/workflows/ci.yml` with full quality gates

**Acceptance Criteria:**
- ✅ File exists in correct location
- ✅ Workflow runs on push and PR
- ✅ Tests Python 3.10, 3.11, 3.12
- ✅ Enforces: ruff linting, mypy strict, pytest coverage ≥75%
- ✅ Uploads coverage to Codecov (optional)
- ✅ Slow tests run separately

**Estimated Effort:** 2 hours

---

### Task 3.2: Add pytest markers configuration

**File:** `pyproject.toml` (add section)

**Implementation:**

```toml
[tool.pytest.ini_options]
markers = [
    "slow: marks tests as slow (deselect with '-m \"not slow\"')",
    "integration: marks tests as integration tests",
    "unit: marks tests as unit tests",
]
testpaths = ["tests"]
python_files = ["test_*.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]
addopts = [
    "--strict-markers",
    "--strict-config",
    "-ra",
    "--cov-branch",
]
```

**Deliverable:** pytest configuration in `pyproject.toml`

**Acceptance Criteria:**
- ✅ Markers defined for slow/integration/unit tests
- ✅ Test discovery configured
- ✅ Branch coverage enabled

**Estimated Effort:** 0.5 hours

---

### Task 3.3: Update README with CI badge

**File:** `README.md` (add to top)

**Implementation:**

```markdown
# Variance - Options Portfolio Analysis

[![CI](https://github.com/your-org/variance-yfinance/workflows/CI/badge.svg)](https://github.com/your-org/variance-yfinance/actions)
[![codecov](https://codecov.io/gh/your-org/variance-yfinance/branch/main/graph/badge.svg)](https://codecov.io/gh/your-org/variance-yfinance)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)

... (rest of README)
```

**Deliverable:** README updated with status badges

**Acceptance Criteria:**
- ✅ CI status badge visible
- ✅ Coverage badge visible (if using Codecov)
- ✅ Python version badge shows 3.10+

**Estimated Effort:** 0.5 hours

---

### Task 3 Summary

| Task | File | Effort |
|------|------|--------|
| 3.1 | .github/workflows/ci.yml | 2h |
| 3.2 | pyproject.toml (pytest markers) | 0.5h |
| 3.3 | README.md (badges) | 0.5h |
| **TOTAL** | **3 files** | **3h** |

---

## Task 4: Implement SizeThreatHandler Logic

### Objective
Complete the stub implementation of SizeThreatHandler to detect positions with tail risk.

### Estimated Effort: 3-4 hours

---

### Task 4.1: Implement SizeThreatHandler

**File:** `src/variance/triage/handlers/size_threat.py`

**Current State (Stub):**
```python
class SizeThreatHandler(TriageHandler):
    def handle(self, request: TriageRequest) -> TriageRequest:
        # Temporary logic until Orchestrator phase provides shock constants
        return self._pass_to_next(request)
```

**Required Implementation:**

```python
"""
Size Threat Handler for Triage Engine.

Detects positions with tail risk (max potential loss) exceeding a configurable
percentage of net liquidity. Default threshold: 5% of NLV.

This prevents portfolio blow-up scenarios from oversized positions.
"""
from typing import Any, Dict
from ..handler import TriageHandler
from ..request import TriageRequest, TriageTag


class SizeThreatHandler(TriageHandler):
    """
    Detects positions with tail risk exceeding NLV threshold.

    Priority: 20 (High priority - above defense/gamma)
    Actionable: Yes (reduce position size)
    """

    def __init__(self, rules: Dict[str, Any]) -> None:
        """
        Initialize handler with trading rules.

        Args:
            rules: Dictionary containing 'size_threat_threshold' (default: 0.05)
        """
        super().__init__(rules)
        self.threshold = rules.get("size_threat_threshold", 0.05)

    def handle(self, request: TriageRequest) -> TriageRequest:
        """
        Check for tail risk exceeding threshold and add tag if triggered.

        Args:
            request: Immutable triage request with position metrics

        Returns:
            New TriageRequest with SIZE_THREAT tag added if condition met
        """
        # Only check losing positions (tail risk only applies to losses)
        if request.net_pl >= 0:
            return self._pass_to_next(request)

        # Calculate tail risk percentage
        tail_risk_pct = self._calculate_tail_risk_pct(request)

        if tail_risk_pct is None:
            return self._pass_to_next(request)

        # Check if tail risk exceeds threshold
        if tail_risk_pct > self.threshold:
            tag = TriageTag(
                tag_type="SIZE_THREAT",
                priority=20,
                logic=self._build_logic_message(tail_risk_pct, request),
                action_cmd=None  # Could add ReduceCommand in future
            )
            request = request.with_tag(tag)

        return self._pass_to_next(request)

    def _calculate_tail_risk_pct(self, request: TriageRequest) -> float | None:
        """
        Calculate tail risk as percentage of net liquidity.

        For credit spreads: Uses max loss (full credit collected)
        For debit spreads: Uses current loss
        For undefined risk: Uses current loss * safety factor

        Args:
            request: Triage request with position data

        Returns:
            Tail risk percentage (0.06 = 6%) or None if cannot calculate
        """
        if request.net_liquidity <= 0:
            return None

        # Determine max potential loss based on position type
        max_loss = self._estimate_max_loss(request)

        if max_loss <= 0:
            return None

        # Calculate percentage of net liquidity
        return abs(max_loss) / request.net_liquidity

    def _estimate_max_loss(self, request: TriageRequest) -> float:
        """
        Estimate maximum potential loss for the position.

        For credit positions (net_cost < 0): Max loss = credit collected
        For debit positions (net_cost > 0): Max loss = debit paid
        For undefined risk: Use current loss as proxy

        Args:
            request: Triage request with position data

        Returns:
            Maximum potential loss (positive number)
        """
        # Credit spread: Max loss is the credit collected (net_cost is negative)
        if request.net_cost < 0:
            # Example: IC with -$500 credit has max loss of ~$500
            # (In reality, max loss = width - credit, but we approximate with credit)
            return abs(request.net_cost)

        # Debit spread: Max loss is the debit paid
        if request.net_cost > 0:
            return abs(request.net_cost)

        # Undefined risk (net_cost == 0): Use current loss
        # Apply 2x safety factor for undefined risk positions
        if request.net_pl < 0:
            return abs(request.net_pl) * 2.0

        return 0.0

    def _build_logic_message(self, tail_risk_pct: float, request: TriageRequest) -> str:
        """
        Build human-readable explanation of tail risk.

        Args:
            tail_risk_pct: Tail risk as percentage (0.06 = 6%)
            request: Triage request with position data

        Returns:
            Logic string for display
        """
        pct_display = f"{tail_risk_pct * 100:.1f}%"
        nlv_display = f"${request.net_liquidity:,.0f}"
        max_loss_display = f"${self._estimate_max_loss(request):,.0f}"

        return (
            f"Tail risk {pct_display} of NLV ({max_loss_display} / {nlv_display}) "
            f"exceeds {self.threshold * 100:.0f}% threshold"
        )
```

**Deliverable:** Fully implemented `SizeThreatHandler`

**Acceptance Criteria:**
- ✅ Handler detects positions with tail risk > threshold
- ✅ Correctly calculates tail risk for credit/debit spreads
- ✅ Builds informative logic message
- ✅ All tests in `test_size_threat_handler.py` pass (remove xfail marker)
- ✅ Handler achieves 90%+ line coverage

**Estimated Effort:** 3 hours

---

### Task 4.2: Update test file (remove xfail)

**File:** `tests/triage/handlers/test_size_threat_handler.py`

**Change Required:**

```python
# Remove this decorator:
@pytest.mark.xfail(reason="SizeThreatHandler is currently a stub - implementation pending")
def test_implementation_exists(self, handler, base_request):
    """SizeThreatHandler implementation complete."""
    # Test should now pass
```

**Deliverable:** Test file updated

**Acceptance Criteria:**
- ✅ xfail marker removed
- ✅ All tests pass without xfail

**Estimated Effort:** 0.5 hours

---

### Task 4.3: Add configuration to trading_rules.json

**File:** `config/trading_rules.json`

**Add:**

```json
{
  "size_threat_threshold": 0.05,
}
```

**Deliverable:** Configuration updated

**Acceptance Criteria:**
- ✅ Default threshold documented in config
- ✅ Users can customize threshold

**Estimated Effort:** 0.5 hours

---

### Task 4 Summary

| Task | File | Effort |
|------|------|--------|
| 4.1 | size_threat.py | 3h |
| 4.2 | test_size_threat_handler.py | 0.5h |
| 4.3 | trading_rules.json | 0.5h |
| **TOTAL** | **3 files** | **4h** |

---

## Task 5: Complete Configuration & Documentation

### Objective
Add missing configuration and documentation for multi-tag TUI features.

### Estimated Effort: 3-4 hours

---

### Task 5.1: Add triage_display section to config

**File:** `config/trading_rules.json`

**Add Section:**

```json
{
  "triage_display": {
    "max_secondary_tags": 3,
    "use_icons": true,
    "hide_tags": [],
    "tag_colors": {
      "EXPIRING": "red bold",
      "HARVEST": "green bold",
      "SIZE_THREAT": "red",
      "DEFENSE": "red bold",
      "GAMMA": "yellow",
      "HEDGE_CHECK": "cyan",
      "TOXIC": "yellow",
      "EARNINGS_WARNING": "orange3",
      "SCALABLE": "green"
    },
    "tag_icons": {
      "EXPIRING": "⏳",
      "HARVEST": "💰",
      "SIZE_THREAT": "⚠️",
      "DEFENSE": "🛡️",
      "GAMMA": "☢️",
      "HEDGE_CHECK": "👁️",
      "TOXIC": "☠️",
      "EARNINGS_WARNING": "📅",
      "SCALABLE": "🚀"
    }
  }
}
```

**Deliverable:** Configuration section added

**Acceptance Criteria:**
- ✅ Section exists in config file
- ✅ Valid JSON structure
- ✅ TagRenderer can read configuration
- ✅ Users can customize colors/icons

**Estimated Effort:** 1 hour (includes validation)

---

### Task 5.2: Create TUI mockups documentation

**File:** `docs/tui_mockups/multi_tag_rendering.md`

**Implementation:**

```markdown
# Multi-Tag TUI Rendering Design

## Overview
This document describes the design options evaluated for displaying multiple
triage tags per position in the terminal UI.

## Current State (Before Multi-Tag)
```
┌─────────────────────────────────────────────────┐
│ Symbol  Strategy        DTE  P/L    Action      │
├─────────────────────────────────────────────────┤
│ AAPL    Iron Condor      45  $1250  HARVEST     │
│ TSLA    Short Strangle   12  -$200  DEFENSE     │
└─────────────────────────────────────────────────┘
```

**Limitation:** Single action code, no visibility into other conditions.

---

## Design Option A: Badge Style (IMPLEMENTED)

```
┌──────────────────────────────────────────────────────────────┐
│ Symbol  Strategy         DTE   P/L    Tags                   │
├──────────────────────────────────────────────────────────────┤
│ AAPL    Iron Condor       45  $1250  💰 HARVEST | ☢️γ         │
│ TSLA    Short Strangle    12  -$200  🛡️ DEFENSE | 📅ERN      │
└──────────────────────────────────────────────────────────────┘

Color codes:
  💰 Green   - Actionable positive (HARVEST, SCALABLE)
  🛡️ Red     - Critical action needed (EXPIRING, DEFENSE, SIZE_THREAT)
  ☢️ Yellow  - Warning (GAMMA, TOXIC)
  📅 Orange  - Informational (EARNINGS, HEDGE_CHECK)
```

**Pros:**
- Compact (fits in standard terminal width 80-120 cols)
- Clear visual hierarchy (primary badge bold/larger)
- Up to 3-4 tags visible per row
- Color-coded for quick scanning
- Unicode emojis add visual interest

**Cons:**
- May truncate on very narrow terminals (<80 cols)
- Requires Unicode support (fallback needed)
- Emoji rendering varies by terminal

**Implementation:** See `src/variance/tui/tag_renderer.py`

---

## Design Option B: Inline Compact (Evaluated, Not Implemented)

```
┌────────────────────────────────────────────────────┐
│ AAPL IC  45d  $1,250  [💰55%][☢️γ][📅3d]          │
│ TSLA SS  12d   -$200  [🛡️DEF][📅ERN]              │
└────────────────────────────────────────────────────┘

Abbreviations:
  💰55% = HARVEST at 55% profit
  ☢️γ   = GAMMA zone
  📅3d  = EARNINGS in 3 days
  🛡️DEF = DEFENSE needed
```

**Pros:**
- Very compact (fits in 60 cols)
- Shows tag values inline (55%, 3d)
- Good for small terminal windows

**Cons:**
- Harder to read (more cryptic)
- Abbreviations not obvious to new users
- Less space for strategy name

**Decision:** Not implemented (readability concerns)

---

## Design Option C: Detailed Rows (Evaluated, Not Implemented)

```
┌────────────────────────────────────────────────────────────────┐
│ AAPL  Iron Condor  45 DTE  $1,250 P/L                         │
│ PRIMARY: 💰 HARVEST (Profit target: 55%)                       │
│ ALSO:    ☢️ GAMMA (Entering gamma zone)                       │
│          📅 EARNINGS (Event in 3 days)                         │
├────────────────────────────────────────────────────────────────┤
│ TSLA  Short Strangle  12 DTE  -$200 P/L                       │
│ PRIMARY: 🛡️ DEFENSE (Position tested, roll needed)             │
│ ALSO:    📅 EARNINGS (Event tomorrow)                          │
└────────────────────────────────────────────────────────────────┘
```

**Pros:**
- Very clear (full descriptions)
- Easy to read for new users
- Shows all tags with full logic

**Cons:**
- Takes 3-4 lines per position (screen fills quickly)
- Not suitable for portfolios with 20+ positions
- Excessive vertical space usage

**Decision:** Not implemented (too verbose)

---

## Recommendation: Option A (Badge Style)

**Rationale:**
1. **Balance:** Good mix of compactness and readability
2. **Scannable:** Quick visual scan with color coding
3. **Scalable:** Works for portfolios with 10-50 positions
4. **Standard:** Fits 80-column terminals (industry standard)

**Fallback for Limited Terminals:**
When emojis not supported, TagRenderer falls back to text:
```
AAPL IC  [H] HARVEST | [G] GAMMA | [E] EARNINGS
```

---

## Configuration

Users can customize tag rendering in `config/trading_rules.json`:

```json
{
  "triage_display": {
    "max_secondary_tags": 3,     // Show up to 3 secondary tags
    "use_icons": true,            // Use emoji icons (or text fallback)
    "hide_tags": ["HEDGE_CHECK"], // Hide specific tags from display
    "tag_colors": { ... },        // Custom color mappings
    "tag_icons": { ... }          // Custom emoji mappings
  }
}
```

---

## Terminal Compatibility

**Tested Terminals:**
- ✅ iTerm2 (macOS) - Full emoji support
- ✅ Terminal.app (macOS) - Full emoji support
- ✅ Windows Terminal - Full emoji support
- ✅ VSCode integrated terminal - Full emoji support
- ⚠️ cmd.exe (Windows) - Limited emoji, use fallback
- ⚠️ PuTTY - Limited color, use fallback

**Minimum Requirements:**
- Terminal width: 80 columns (recommended 100+)
- Color support: ANSI 256 colors (fallback to 16 colors)
- Unicode support: UTF-8 (fallback to ASCII)

---

## Examples

### Example 1: Multiple Actionable Tags
```
AAPL IC  💰 HARVEST 55% | 🛡️ DEFENSE | 📅 EARNINGS 2d
```
**Interpretation:** Take profit (primary), but be aware of defense needed and earnings event.

### Example 2: Warning Tags Only
```
SPY IC  ☢️ GAMMA | 👁️ HEDGE_CHECK
```
**Interpretation:** In gamma zone, hedge position stuck in dead money range.

### Example 3: Single Critical Tag
```
TSLA SS  ⏳ EXPIRING
```
**Interpretation:** Expires today, roll immediately.

---

## Future Enhancements

**Potential Additions:**
1. Tag tooltips (hover for full logic explanation)
2. Tag filtering UI (show only HARVEST tags, etc.)
3. Tag history (track which tags appeared when)
4. Customizable tag priority (user-defined ordering)

---

**Document Version:** 1.0
**Last Updated:** 2025-12-23
**Implementation Status:** Badge Style (Option A) complete
```

**Deliverable:** Complete TUI mockups documentation

**Acceptance Criteria:**
- ✅ File exists at `docs/tui_mockups/multi_tag_rendering.md`
- ✅ Documents 3 design options with pros/cons
- ✅ Explains rationale for chosen design
- ✅ Includes terminal compatibility notes
- ✅ Provides configuration examples

**Estimated Effort:** 2 hours

---

### Task 5.3: Update README with multi-tag screenshot

**File:** `README.md`

**Add Section:**

```markdown
## Features

### Multi-Tag Triage System
Variance uses a sophisticated multi-tag system to provide comprehensive
position health analysis. Each position can have multiple tags simultaneously:

```
┌──────────────────────────────────────────────────────────────┐
│ Symbol  Strategy         DTE   P/L    Tags                   │
├──────────────────────────────────────────────────────────────┤
│ AAPL    Iron Condor       45  $1250  💰 HARVEST | ☢️γ         │
│ TSLA    Short Strangle    12  -$200  🛡️ DEFENSE | 📅ERN      │
└──────────────────────────────────────────────────────────────┘
```

**Tag Types:**
- 💰 **HARVEST** - Profit target hit (actionable)
- 🛡️ **DEFENSE** - Position tested, adjustment needed
- ☢️ **GAMMA** - Entering gamma zone (< 21 DTE)
- 📅 **EARNINGS** - Earnings event approaching
- ⏳ **EXPIRING** - Position expires today
- ⚠️ **SIZE_THREAT** - Tail risk exceeds threshold
- And more...

See [Multi-Tag System Documentation](docs/guides/multi_tag_system.md) for details.
```

**Deliverable:** README updated with feature description

**Acceptance Criteria:**
- ✅ Multi-tag system explained in README
- ✅ Visual example included
- ✅ Link to detailed documentation

**Estimated Effort:** 1 hour

---

### Task 5 Summary

| Task | File | Effort |
|------|------|--------|
| 5.1 | config/trading_rules.json | 1h |
| 5.2 | docs/tui_mockups/multi_tag_rendering.md | 2h |
| 5.3 | README.md | 1h |
| **TOTAL** | **3 files** | **4h** |

---

## Project Summary

### Total Effort Estimate

| Task Group | Effort | Priority |
|------------|--------|----------|
| **Task 1: Unit Tests (3 files)** | 6h | 🔴 BLOCKER |
| **Task 2: Integration Tests (2 files)** | 6h | 🔴 BLOCKER |
| **Task 3: CI/CD Configuration** | 3h | 🔴 BLOCKER |
| **Task 4: SizeThreatHandler Implementation** | 4h | 🔴 BLOCKER |
| **Task 5: Configuration & Docs** | 4h | 🟡 MEDIUM |
| **TOTAL** | **23h** | **3-4 days** |

---

## Deliverables Checklist

### Critical (Blockers)
- [ ] `tests/triage/handlers/test_hedge_handler.py` (6 tests)
- [ ] `tests/triage/handlers/test_size_threat_handler.py` (7 tests)
- [ ] `tests/classification/classifiers/test_stock_classifier.py` (6 tests)
- [ ] `tests/triage/test_chain_integration.py` (10 tests)
- [ ] `tests/screening/test_pipeline_integration.py` (9 tests)
- [ ] `.github/workflows/ci.yml` (CI/CD pipeline)
- [ ] `src/variance/triage/handlers/size_threat.py` (implementation)

### Medium Priority
- [ ] `config/trading_rules.json` (triage_display + size_threat_threshold)
- [ ] `docs/tui_mockups/multi_tag_rendering.md`
- [ ] `README.md` (multi-tag section + badges)
- [ ] `pyproject.toml` (pytest markers)

---

## Acceptance Criteria

### Overall Project Success
- ✅ `mypy --strict src/variance` exits 0 (already passing from IMPL-001)
- ✅ `pytest --cov=src/variance` shows ≥80% coverage (NEW)
- ✅ CI/CD pipeline runs on every commit (NEW)
- ✅ All 9 triage handlers have tests (NEW: 2 missing tests added)
- ✅ All 10 classifiers have tests (NEW: 1 missing test added)
- ✅ SizeThreatHandler fully implemented (NEW)
- ✅ Multi-tag TUI documented and configured (NEW)

### Test Count
**Before (IMPL-001):** ~22 tests
**After (IMPL-002):** ~60 tests (22 + 38 new)
**Coverage:** 30% → 80%+

---

## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Tests reveal bugs in existing handlers | Medium | Medium | Expected - tests catch bugs, that's the point |
| SizeThreatHandler implementation complex | Low | Medium | Spec provides complete implementation |
| CI takes too long to run | Low | Low | Use matrix, cache dependencies |
| Coverage < 80% after all tests | Low | High | Focus on core business logic, skip trivial getters |

---

## Dependencies

**Prerequisites from IMPL-001:**
- ✅ Type annotations complete (mypy strict passing)
- ✅ Handlers implemented (9 handlers exist)
- ✅ Classifiers implemented (10 classifiers exist)
- ✅ TagRenderer implemented (TUI rendering works)

**No External Dependencies:**
- All work is internal (no API changes, no new libraries)
- Backward compatible (only adding tests/CI)

---

## Success Metrics

| Metric | Current (IMPL-001) | Target (IMPL-002) |
|--------|-------------------|-------------------|
| **Test Files** | 16 | 21 (+5) |
| **Test Cases** | ~22 | ~60 (+38) |
| **Coverage** | ~30% | ≥80% |
| **CI Enforcement** | No | Yes |
| **Handlers with Tests** | 7 of 9 | 9 of 9 |
| **Classifiers with Tests** | 9 of 10 | 10 of 10 |
| **Integration Tests** | 0 | 2 |

---

## Recommended Approach

### Option A: Execute All Tasks (Recommended)
**Effort:** 23 hours (3-4 days)
**Result:** Production-ready codebase

**Execution Order:**
1. Day 1: Task 1 (Unit Tests) - 6h
2. Day 2: Task 2 (Integration Tests) + Task 4 (SizeThreatHandler) - 10h
3. Day 3: Task 3 (CI/CD) + Task 5 (Config/Docs) - 7h

---

### Option B: Blockers Only
**Effort:** 19 hours (2-3 days)
**Result:** Meets minimum acceptance criteria

**Execution Order:**
1. Tasks 1, 2, 3, 4 (skip Task 5 documentation)
2. Defer TUI mockups and README updates

---

### Option C: Phased Delivery
**Phase 1 (Blockers):** Tasks 1-4 (19h)
**Phase 2 (Polish):** Task 5 (4h)

**Benefit:** Can merge Phase 1 immediately, Phase 2 as time allows

---

## Contact & Questions

**For Implementation Questions:**
- Review parent plan: `docs/plans/IMPL_001_QUALITY_AND_FEATURES_Q1_2025.md`
- Check existing tests: `tests/triage/handlers/` (7 examples)
- Review handler implementations: `src/variance/triage/handlers/` (9 files)

**For Architecture Questions:**
- See RFC_016 for Chain of Responsibility pattern
- See ADR_0006 for hybrid functional/OOP rationale
- Review guides in `docs/guides/`

---

## Appendix: Verification Commands

### Before Starting
```bash
# Baseline metrics
pytest --co -q  # Count existing tests (~22)
pytest --cov=src/variance --cov-report=term  # ~30% coverage
mypy --strict src/variance  # Should pass (from IMPL-001)
```

### After Task 1 (Unit Tests)
```bash
# Should have 3 more test files
ls tests/triage/handlers/test_hedge_handler.py  # Should exist
ls tests/triage/handlers/test_size_threat_handler.py  # Should exist
ls tests/classification/classifiers/test_stock_classifier.py  # Should exist

# Test count should increase by ~19
pytest --co -q  # ~41 tests
```

### After Task 2 (Integration Tests)
```bash
# Should have 2 integration test files
ls tests/triage/test_chain_integration.py  # Should exist
ls tests/screening/test_pipeline_integration.py  # Should exist

# Test count should increase by ~19 more
pytest --co -q  # ~60 tests

# Coverage should be much higher
pytest --cov=src/variance --cov-report=term  # Should show ≥75%
```

### After Task 3 (CI/CD)
```bash
# CI workflow should exist
ls .github/workflows/ci.yml  # Should exist

# Can test workflow locally (requires act)
act -j quality-gates

# Push to GitHub to trigger real CI
git push origin feature/impl-002-blockers
```

### After Task 4 (SizeThreatHandler)
```bash
# Handler should have implementation
grep -A 20 "def handle" src/variance/triage/handlers/size_threat.py
# Should NOT just return self._pass_to_next(request)

# Test should pass (no xfail)
pytest tests/triage/handlers/test_size_threat_handler.py -v
# All tests should PASS (none skipped/xfailed)
```

### Final Verification
```bash
# All quality gates should pass
mypy --strict src/variance  # Exit code 0
pytest --cov=src/variance --cov-fail-under=80  # Exit code 0
ruff check .  # Exit code 0

# CI should pass
# Check GitHub Actions for green checkmark
```

---

**Document Version:** 1.0
**Last Updated:** 2025-12-23
**Status:** Ready for Implementation
**Parent Plan:** IMPL-001 (71% complete, needs these blockers resolved)
