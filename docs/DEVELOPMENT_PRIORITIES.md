# Development Priorities & Backlog

**Last Updated:** December 25, 2024

## Critical Issues (Do First)

### 1. Fix Failing Integration Tests (7 tests)
**Impact:** High - Tests are broken, CI/CD blocked

**Failing Tests:**
- `test_futures_proxy_correlation.py::test_multiple_futures_with_different_correlations`
- `test_get_market_data.py::test_get_iv_happy_path`
- `test_market_data_service.py::test_service_checks_cache_first`
- `test_market_data_service.py::test_service_fetches_missing`
- `test_signal_synthesis.py::test_score_calculation_balanced`
- `test_signal_synthesis.py::test_score_cheap_vol_is_high`
- `test_signal_synthesis.py::test_score_fallback_tactical`

**Root Cause:** Market data dependencies - tests expect live data or cached responses

**Solution:**
- Add proper mocking for external API calls
- Create fixtures for market data responses
- Use `pytest-vcr` to record/replay API interactions
- Add `@pytest.mark.integration` and skip during unit test runs

**Effort:** 2-4 hours
**Files:** `tests/test_*.py`

### 2. Tastytrade Client Test Coverage (14% → 70%)
**Impact:** High - Core integration point, currently untested

**Current Coverage:** 14% (147/176 lines uncovered)
**Target:** 70%+

**Areas to Test:**
- Authentication flow
- IV data fetching
- Option chain retrieval
- Liquidity rating lookup
- Error handling (rate limits, auth failures, malformed responses)
- Caching behavior

**Approach:**
- Mock HTTP responses using `responses` or `pytest-vcr`
- Test happy path, error cases, edge cases
- Verify cache hit/miss logic

**Effort:** 4-6 hours
**Files:** `tests/test_tastytrade_client.py` (create), `src/variance/tastytrade_client.py`

## High Priority (Next)

### 3. Strategy Implementation Tests (22-26% → 70%)
**Impact:** Medium - Strategy detection is core functionality

**Current Coverage:**
- Butterfly: 26%
- Time Spread: 22%

**What to Test:**
- Detection logic (`matches()` method)
- Breakeven calculations
- Edge cases (missing strikes, unusual leg counts)
- Max loss/profit calculations

**Effort:** 3-4 hours
**Files:** `tests/strategies/test_butterfly.py`, `tests/strategies/test_time_spread.py`

### 4. Vol Screener CLI Tests (56% → 80%)
**Impact:** Medium - Main entry point

**Current Gaps:**
- CLI argument parsing
- Output formatting (JSON vs TUI)
- Error handling (missing config, invalid universe)
- Integration with screening pipeline

**Effort:** 2-3 hours
**Files:** `tests/test_vol_screener.py`, `src/variance/vol_screener.py`

### 5. Resource Leak Warnings (SQLite)
**Impact:** Low - Doesn't affect functionality, clutters test output

**Issue:** Unclosed database connections in cache/tests
```
ResourceWarning: unclosed database in <sqlite3.Connection object at 0x...>
```

**Solution:**
- Ensure all cache connections use context managers
- Add `__del__` methods or `close()` calls
- Use `@pytest.fixture(scope="function")` with cleanup

**Effort:** 1-2 hours
**Files:** Cache-related modules

## Medium Priority (Soon)

### 6. Create ScalableHandler Implementation
**Impact:** Medium - Handler referenced but never implemented

**Current State:**
- Test file existed but was removed (stale)
- Handler not in `src/variance/triage/handlers/`
- ScalableGateSpec exists for filtering, but no handler for triage

**What it Should Do:**
- Check if held position edge has expanded (VRP Tactical Markup >= 1.35)
- Tag positions as "SCALABLE" for size increase
- Recommend scaling action

**Effort:** 2-3 hours
**Files:** `src/variance/triage/handlers/scalable.py`, `tests/triage/handlers/test_scalable_handler.py`

### 7. Improve Triage Engine Coverage (82% → 90%)
**Impact:** Low - Already high coverage

**Gaps:**
- Edge cases in position parsing
- Error handling paths
- Multi-leg strategy edge cases

**Effort:** 2-3 hours
**Files:** `tests/test_triage_engine.py`

### 8. Strategy Detector Edge Cases (74% → 85%)
**Impact:** Low - Already decent coverage

**What to Add:**
- Ambiguous leg detection (could be multiple strategies)
- Malformed positions
- Unusual strike spacings
- Weekly vs monthly expirations

**Effort:** 2-3 hours
**Files:** `tests/test_strategy_detector.py`

## Low Priority (Nice to Have)

### 9. Portfolio Parser Edge Cases (90% → 95%)
**Impact:** Low - Already high coverage

**Gaps:**
- Missing required fields
- Invalid date formats
- Duplicate legs

**Effort:** 1-2 hours

### 10. Correlation Filter Utilization
**Impact:** Low - Feature exists but underused

**Current State:** CorrelationSpec exists, not actively used in screening

**Opportunity:** Enable sector-based correlation filtering to avoid over-concentration

**Effort:** 3-4 hours (design + implementation)

### 11. Documentation Completeness
**Impact:** Low - Docs are already good

**Gaps:**
- Examples for each strategy type
- Troubleshooting guide for common errors
- Video walkthrough (if applicable)

**Effort:** 2-4 hours

## Future Enhancements (Backlog)

### Performance Optimization
- Cache warming on startup
- Parallel market data fetching
- Reduce yfinance API calls further

### Features
- Backtesting framework
- Historical VRP analysis
- Position sizing recommendations
- Risk-adjusted scoring

### Infrastructure
- Docker containerization
- CI/CD pipeline
- Automated deployment
- Monitoring/alerting

## Estimated Effort Summary

| Priority | Task | Effort | Impact |
|----------|------|--------|--------|
| Critical | Fix failing tests | 2-4h | High |
| Critical | Tastytrade client tests | 4-6h | High |
| High | Strategy tests | 3-4h | Medium |
| High | Vol screener tests | 2-3h | Medium |
| High | SQLite leak warnings | 1-2h | Low |
| Medium | ScalableHandler | 2-3h | Medium |
| Medium | Triage engine polish | 2-3h | Low |
| Medium | Strategy detector | 2-3h | Low |

**Total Critical + High Priority:** ~16-22 hours

## Recommended Approach

**Week 1: Stabilize**
1. Fix failing integration tests (mock dependencies)
2. Address resource leak warnings
3. Verify all quality gates pass

**Week 2: Core Coverage**
4. Tastytrade client comprehensive tests
5. Strategy implementation tests
6. Vol screener CLI tests

**Week 3: Polish**
7. ScalableHandler implementation
8. Triage engine edge cases
9. Documentation gaps

## Testing Best Practices

### Unit Tests
- **Fast:** < 1ms each
- **Isolated:** No external dependencies
- **Mocked:** All API calls, file I/O, random data
- **Deterministic:** Same input = same output

### Integration Tests
- **Mark explicitly:** `@pytest.mark.integration`
- **Use fixtures:** Consistent test data
- **Skip when needed:** `@pytest.mark.skipif(condition)`
- **Clean up:** Restore state after tests

### Coverage Goals
- **Core modules:** 85%+
- **Utilities:** 70%+
- **UI/CLI:** 50%+ (harder to test)
- **Overall:** 75%+

### Mocking Strategy
```python
# Good: Mock external dependencies
@mock.patch('variance.tastytrade_client.requests.post')
def test_api_call(mock_post):
    mock_post.return_value.json.return_value = {"iv": 30.0}
    result = fetch_iv("AAPL")
    assert result == 30.0

# Bad: Don't mock internal logic
@mock.patch('variance.models.market_specs.VrpStructuralSpec.is_satisfied_by')
def test_filter(mock_spec):  # This defeats the purpose of testing!
    mock_spec.return_value = True
```

## Quality Metrics

**Current State:**
- Test Coverage: 64%
- Passing Tests: 411/418 (98.3%)
- Complexity: All modules < 10 (Grade B)
- Type Safety: Strict mypy passing

**Target State:**
- Test Coverage: 75%+
- Passing Tests: 100%
- Complexity: All < 10
- Type Safety: Strict mypy passing
- No resource warnings

## Success Criteria

A handoff is successful when:
1. ✅ All tests pass (0 failures)
2. ✅ Coverage >= 75%
3. ✅ All quality gates pass (ruff, mypy, radon)
4. ✅ No resource warnings
5. ✅ Tastytrade client tested
6. ✅ Documentation complete
7. ✅ New developer can onboard in < 1 day
