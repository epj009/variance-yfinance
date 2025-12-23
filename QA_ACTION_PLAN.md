# QA ACTION PLAN: Domain Objects & Strategy Pattern Test Coverage
**Date:** 2025-12-23
**Priority:** CRITICAL
**Estimated Effort:** 16-20 hours over 2 weeks
**Target Coverage:** 69% -> 85%+

---

## EXECUTIVE SUMMARY

Following the major refactor implementing Domain Objects and Strategy Pattern, the test suite has **critical gaps**:
- **Domain Objects (Position, Cluster, Portfolio):** 0 dedicated unit tests
- **Strategy Pattern (BaseStrategy, ShortThetaStrategy, Factory):** 0 dedicated unit tests
- **Overall Coverage:** 69% (target: 80%+)

All 271 tests are passing, but the new architecture is **only validated through integration tests**. This report provides a concrete action plan to close these gaps.

---

## WEEK 1: DOMAIN OBJECTS (10 hours)

### Day 1-2: Position Tests (4 hours)

**File:** `/Users/eric.johnson@verinext.com/Projects/variance-yfinance/tests/test_position.py`

**Tests to Implement:**
1. `test_from_row_creates_position_with_valid_data` - Happy path factory method
2. `test_from_row_handles_missing_optional_fields` - Minimal required fields
3. `test_root_symbol_property_for_equity` - Extract root from "AAPL 250117P150"
4. `test_root_symbol_property_for_futures` - Extract root from "/ES JAN25"
5. `test_root_symbol_property_for_micro_futures` - Extract root from "/MES JAN25"
6. `test_is_option_property_returns_true_for_options` - asset_type="Option"
7. `test_is_stock_property_returns_true_for_stock` - asset_type="Stock"
8. `test_is_short_property_identifies_negative_quantity` - quantity < 0
9. `test_is_long_property_identifies_positive_quantity` - quantity > 0
10. `test_position_immutability` - Frozen dataclass prevents modification
11. `test_from_row_with_none_strike_for_stock` - Stock has no strike
12. `test_from_row_with_malformed_numeric_values` - "N/A" in Quantity field

**Expected Coverage:** position.py: 90% -> 100%

**Command to Run:**
```bash
pytest tests/test_position.py -v --cov=src/variance/models/position.py --cov-report=term-missing
```

---

### Day 3-4: Cluster Tests (4 hours)

**File:** `/Users/eric.johnson@verinext.com/Projects/variance-yfinance/tests/test_cluster.py`

**Tests to Implement:**
1. `test_cluster_calculates_net_pl_correctly` - Sum of leg pl_open
2. `test_cluster_calculates_net_cost_correctly` - Sum of leg cost
3. `test_cluster_calculates_total_delta` - Sum of leg beta_delta
4. `test_cluster_calculates_total_theta` - Sum of leg theta
5. `test_cluster_min_dte_only_considers_options` - Stock legs ignored
6. `test_cluster_min_dte_with_no_options_returns_zero` - All stock legs
7. `test_cluster_name_identifies_short_strangle` - 2 short options, different strikes
8. `test_cluster_name_identifies_iron_condor` - 4 legs, balanced
9. `test_cluster_strategy_id_maps_credit_correctly` - net_cost < 0
10. `test_cluster_strategy_id_maps_debit_correctly` - net_cost > 0
11. `test_cluster_with_empty_legs_list` - Edge case: no legs
12. `test_cluster_with_single_leg` - Edge case: 1 leg

**Expected Coverage:** cluster.py: 69% -> 100%

**Command to Run:**
```bash
pytest tests/test_cluster.py -v --cov=src/variance/models/cluster.py --cov-report=term-missing
```

---

### Day 5: Portfolio Tests (2 hours)

**File:** `/Users/eric.johnson@verinext.com/Projects/variance-yfinance/tests/test_portfolio.py`

**Tests to Implement:**
1. `test_portfolio_total_theta_aggregates_clusters` - Sum of cluster.total_theta
2. `test_portfolio_total_delta_aggregates_clusters` - Sum of cluster.total_delta
3. `test_portfolio_cluster_count` - len(clusters)
4. `test_portfolio_with_empty_clusters` - Edge case: no clusters
5. `test_portfolio_with_negative_net_liquidity` - Edge case: negative value
6. `test_portfolio_initialization_defaults` - Default net_liquidity and rules
7. `test_portfolio_with_single_cluster` - Edge case: 1 cluster
8. `test_portfolio_with_multiple_clusters` - 3+ clusters

**Expected Coverage:** portfolio.py: 82% -> 100%

**Command to Run:**
```bash
pytest tests/test_portfolio.py -v --cov=src/variance/models/portfolio.py --cov-report=term-missing
```

---

## WEEK 2: STRATEGY PATTERN (10 hours)

### Day 6-7: BaseStrategy Tests (3 hours)

**File:** `/Users/eric.johnson@verinext.com/Projects/variance-yfinance/tests/test_base_strategy.py`

**Tests to Implement:**
1. `test_check_harvest_at_50pct_profit` - Exactly at target
2. `test_check_harvest_above_50pct_profit` - 75% profit
3. `test_check_harvest_velocity_25pct_in_3days` - Early win
4. `test_check_harvest_velocity_25pct_in_5days` - Boundary condition
5. `test_check_harvest_no_action_below_target` - 30% profit, no harvest
6. `test_check_harvest_no_action_velocity_too_slow` - 25% in 10 days
7. `test_strategy_initialization_uses_config` - profit_target_pct from config
8. `test_strategy_initialization_uses_defaults` - Fallback to rules
9. `test_check_toxic_theta_returns_none_for_base` - Base class no-op
10. `test_is_tested_raises_not_implemented` - Abstract method enforcement

**Expected Coverage:** base.py: 82% -> 100%

**Command to Run:**
```bash
pytest tests/test_base_strategy.py -v --cov=src/variance/strategies/base.py --cov-report=term-missing
```

---

### Day 8-9: ShortThetaStrategy Tests (4 hours)

**File:** `/Users/eric.johnson@verinext.com/Projects/variance-yfinance/tests/test_short_theta_strategy.py`

**Tests to Implement:**
1. `test_is_tested_short_put_itm` - Price < strike for put
2. `test_is_tested_short_put_otm` - Price > strike for put
3. `test_is_tested_short_call_itm` - Price > strike for call
4. `test_is_tested_short_call_otm` - Price < strike for call
5. `test_is_tested_ignores_long_legs` - qty > 0 never tested
6. `test_is_tested_ignores_stock_legs` - Type="Stock" never tested
7. `test_check_toxic_theta_low_efficiency` - Carry/cost < 0.10
8. `test_check_toxic_theta_normal_efficiency` - Carry/cost >= 0.10
9. `test_check_toxic_theta_debit_trade_skipped` - cluster_theta <= 0
10. `test_check_toxic_theta_uses_hv_floor` - HV < 5% floored to 5%
11. `test_check_toxic_theta_missing_hv_returns_none` - No HV data
12. `test_check_toxic_theta_missing_price_returns_none` - Price <= 0
13. `test_check_toxic_theta_zero_gamma_returns_none` - Edge case
14. `test_inherits_check_harvest_from_base` - Verify base class logic

**Expected Coverage:** short_theta.py: 97% -> 100%

**Command to Run:**
```bash
pytest tests/test_short_theta_strategy.py -v --cov=src/variance/strategies/short_theta.py --cov-report=term-missing
```

---

### Day 10: StrategyFactory Tests (3 hours)

**File:** `/Users/eric.johnson@verinext.com/Projects/variance-yfinance/tests/test_strategy_factory.py`

**Tests to Implement:**
1. `test_factory_returns_short_theta_for_short_strangle` - Known ID
2. `test_factory_returns_short_theta_for_iron_condor` - Known ID
3. `test_factory_returns_short_theta_for_jade_lizard` - Known ID
4. `test_factory_returns_short_theta_for_undefined_type` - Type="undefined"
5. `test_factory_returns_short_theta_for_short_vol_type` - Type="short_vol"
6. `test_factory_returns_short_theta_for_neutral_type` - Type="neutral"
7. `test_factory_returns_default_for_long_strategies` - Long call/put
8. `test_factory_returns_short_theta_for_none_id` - Unknown strategy
9. `test_factory_passes_config_to_strategy` - Verify config propagation
10. `test_factory_passes_rules_to_strategy` - Verify rules propagation
11. `test_factory_with_missing_strategy_config` - Empty config dict

**Expected Coverage:** factory.py: 75% -> 100%

**Command to Run:**
```bash
pytest tests/test_strategy_factory.py -v --cov=src/variance/strategies/factory.py --cov-report=term-missing
```

---

## CRITICAL FIXES (Immediate)

### Fix 1: Database Connection Leak (15 minutes)

**File:** `/Users/eric.johnson@verinext.com/Projects/variance-yfinance/tests/conftest.py`
**Line:** 37-58

**Current Code:**
```python
@pytest.fixture
def temp_cache_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test_cache.db"
    monkeypatch.setattr(get_market_data, 'DB_PATH', str(db_path))
    fresh_cache = get_market_data.MarketCache(str(db_path))
    monkeypatch.setattr(get_market_data, 'cache', fresh_cache)
    return db_path
```

**Fixed Code:**
```python
@pytest.fixture
def temp_cache_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test_cache.db"
    monkeypatch.setattr(get_market_data, 'DB_PATH', str(db_path))
    fresh_cache = get_market_data.MarketCache(str(db_path))
    monkeypatch.setattr(get_market_data, 'cache', fresh_cache)

    yield db_path

    # Explicit cleanup to prevent ResourceWarning
    try:
        fresh_cache.conn.close()
    except Exception:
        pass  # Already closed or doesn't exist
```

**Verification:**
```bash
pytest tests/ -v 2>&1 | grep -c "ResourceWarning"
# Should output: 0
```

---

### Fix 2: Add Domain Object Fixtures (1 hour)

**File:** `/Users/eric.johnson@verinext.com/Projects/variance-yfinance/tests/conftest.py`
**Insert After Line:** 276

**Code to Add:**
```python
from variance.models import Position, StrategyCluster, Portfolio

@pytest.fixture
def make_position():
    """Factory for Position domain objects."""
    def _make(**kwargs) -> Position:
        defaults = {
            "symbol": "AAPL",
            "asset_type": "Option",
            "quantity": -1.0,
            "strike": 150.0,
            "dte": 45,
            "exp_date": "2025-01-17",
            "call_put": "Put",
            "underlying_price": 155.0,
            "pl_open": 50.0,
            "cost": -100.0,
            "delta": 10.0,
            "beta_delta": 10.0,
            "theta": -2.0,
            "gamma": 0.05,
            "vega": 5.0,
            "bid": 1.00,
            "ask": 1.10,
            "mark": 1.05,
            "raw_data": None,
        }
        return Position(**{**defaults, **kwargs})
    return _make


@pytest.fixture
def make_cluster(make_position):
    """Factory for StrategyCluster domain objects."""
    def _make(legs: list[Position] = None, **kwargs) -> StrategyCluster:
        if legs is None:
            # Default: Short Strangle (2 short options, different strikes)
            legs = [
                make_position(call_put="Put", strike=145.0, cost=-50.0, pl_open=25.0),
                make_position(call_put="Call", strike=155.0, cost=-50.0, pl_open=25.0),
            ]
        return StrategyCluster(legs=legs, **kwargs)
    return _make


@pytest.fixture
def make_portfolio(make_cluster):
    """Factory for Portfolio domain objects."""
    def _make(
        clusters: list[StrategyCluster] = None,
        net_liquidity: float = 50000.0,
        rules: dict = None,
        **kwargs
    ) -> Portfolio:
        if clusters is None:
            clusters = [make_cluster()]
        if rules is None:
            rules = {}

        return Portfolio(
            clusters=clusters,
            net_liquidity=net_liquidity,
            rules=rules,
            **kwargs
        )
    return _make


@pytest.fixture
def mock_short_theta_strategy(mock_trading_rules):
    """Returns a configured ShortThetaStrategy instance."""
    from variance.strategies.short_theta import ShortThetaStrategy

    config = {
        "metadata": {
            "name": "Short Strangle",
            "type": "short_vol",
            "gamma_trigger_dte": 21,
            "earnings_stance": "avoid",
        },
        "management": {
            "profit_target_pct": 0.50,
            "defense_mechanic": "roll_untested",
        },
    }

    return ShortThetaStrategy(
        strategy_id="short_strangle",
        config=config,
        rules=mock_trading_rules,
    )
```

**Verification:**
```bash
pytest tests/test_position.py::test_position_factory_fixture -v
pytest tests/test_cluster.py::test_cluster_factory_fixture -v
pytest tests/test_portfolio.py::test_portfolio_factory_fixture -v
```

---

## REGRESSION TESTS (1 hour)

### File: `/Users/eric.johnson@verinext.com/Projects/variance-yfinance/tests/test_regression_recent_fixes.py`

**Tests to Implement:**
1. `test_vol_screener_no_name_errors` - Prevent NameError re-introduction (commit 56b9183)
2. `test_screener_limits_config_driven` - Verify limit behavior (commit 20a7a87)
3. `test_domain_objects_backward_compatibility` - Old dict API still works (commit 28806ca)
4. `test_strategy_pattern_action_code_parity` - Triage actions unchanged (commit a46762b)
5. `test_analyze_portfolio_returns_same_structure` - Output schema unchanged

**Command to Run:**
```bash
pytest tests/test_regression_recent_fixes.py -v
```

---

## VERIFICATION & ROLLOUT

### Step 1: Run Individual Test Files
```bash
# Week 1
pytest tests/test_position.py -v --cov=src/variance/models/position.py --cov-report=term-missing
pytest tests/test_cluster.py -v --cov=src/variance/models/cluster.py --cov-report=term-missing
pytest tests/test_portfolio.py -v --cov=src/variance/models/portfolio.py --cov-report=term-missing

# Week 2
pytest tests/test_base_strategy.py -v --cov=src/variance/strategies/base.py --cov-report=term-missing
pytest tests/test_short_theta_strategy.py -v --cov=src/variance/strategies/short_theta.py --cov-report=term-missing
pytest tests/test_strategy_factory.py -v --cov=src/variance/strategies/factory.py --cov-report=term-missing

# Regression
pytest tests/test_regression_recent_fixes.py -v
```

### Step 2: Run Full Test Suite
```bash
pytest tests/ -v --cov=src/variance --cov-report=term-missing --cov-report=html
```

**Expected Results:**
- Tests: 271 -> 321+ (50 new tests)
- Coverage: 69% -> 85%+
- ResourceWarnings: 33 -> 0
- Pass Rate: 100%

### Step 3: Review HTML Coverage Report
```bash
open htmlcov/index.html
```

**Look for:**
- position.py: 100% coverage
- cluster.py: 100% coverage
- portfolio.py: 100% coverage
- base.py: 100% coverage
- short_theta.py: 100% coverage
- factory.py: 100% coverage

### Step 4: Commit Changes
```bash
git add tests/test_position.py tests/test_cluster.py tests/test_portfolio.py
git add tests/test_base_strategy.py tests/test_short_theta_strategy.py tests/test_strategy_factory.py
git add tests/test_regression_recent_fixes.py
git add tests/conftest.py

git commit -m "Test: Add comprehensive Domain Object and Strategy Pattern test suites

- Add test_position.py (12 tests, 100% coverage)
- Add test_cluster.py (12 tests, 100% coverage)
- Add test_portfolio.py (8 tests, 100% coverage)
- Add test_base_strategy.py (10 tests, 100% coverage)
- Add test_short_theta_strategy.py (14 tests, 100% coverage)
- Add test_strategy_factory.py (11 tests, 100% coverage)
- Add test_regression_recent_fixes.py (5 tests)
- Add Domain Object fixtures to conftest.py
- Fix database connection leak in temp_cache_db fixture

Coverage: 69% -> 85%+
Tests: 271 -> 321+
ResourceWarnings: 33 -> 0

Closes critical gaps from QA Audit Report 2024-12-23."
```

---

## SUCCESS CRITERIA

**MUST ACHIEVE:**
- [ ] 50+ new tests added
- [ ] All new tests passing (100% pass rate)
- [ ] Coverage >= 85% overall
- [ ] Domain Objects: 100% coverage
- [ ] Strategy Pattern: 100% coverage
- [ ] 0 ResourceWarnings

**SHOULD ACHIEVE:**
- [ ] All test files created as specified
- [ ] Domain Object fixtures in conftest.py
- [ ] Database leak fixed
- [ ] Regression tests for recent fixes

**NICE TO HAVE:**
- [ ] Test suite reorganization (unit/, integration/)
- [ ] Performance benchmarks added
- [ ] Property-based tests (hypothesis)

---

## TIMELINE

**Week 1: Domain Objects**
- Day 1-2: test_position.py (4 hours)
- Day 3-4: test_cluster.py (4 hours)
- Day 5: test_portfolio.py (2 hours)

**Week 2: Strategy Pattern**
- Day 6-7: test_base_strategy.py (3 hours)
- Day 8-9: test_short_theta_strategy.py (4 hours)
- Day 10: test_strategy_factory.py (3 hours)

**Immediate (Today):**
- Fix database leak (15 minutes)
- Add fixtures to conftest.py (1 hour)
- Add regression tests (1 hour)

**Total Effort:** 16-20 hours over 2 weeks

---

## CONTACTS & RESOURCES

**Files to Create:**
```
tests/test_position.py
tests/test_cluster.py
tests/test_portfolio.py
tests/test_base_strategy.py
tests/test_short_theta_strategy.py
tests/test_strategy_factory.py
tests/test_regression_recent_fixes.py
```

**Files to Modify:**
```
tests/conftest.py (add fixtures, fix leak)
```

**Reference Documentation:**
- QA Audit Report: `/Users/eric.johnson@verinext.com/Projects/variance-yfinance/QA_AUDIT_REPORT_2024-12-23.md`
- Source Code: `/Users/eric.johnson@verinext.com/Projects/variance-yfinance/src/variance/models/`
- Source Code: `/Users/eric.johnson@verinext.com/Projects/variance-yfinance/src/variance/strategies/`

**Pytest Documentation:**
- Fixtures: https://docs.pytest.org/en/stable/fixture.html
- Coverage: https://pytest-cov.readthedocs.io/
- Parametrize: https://docs.pytest.org/en/stable/parametrize.html

---

**END OF ACTION PLAN**

**Status:** READY FOR IMPLEMENTATION
**Priority:** CRITICAL
**Estimated Completion:** 2 weeks from start
**Next Review:** After Week 1 (Domain Objects complete)
