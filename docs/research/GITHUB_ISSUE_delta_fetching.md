# [ENHANCEMENT] Delta/Incremental Fetching for Historical Market Data

**Labels:** `enhancement`, `performance`, `optimization`, `backlog`

**Priority:** Low (P3)

**Milestone:** Future / Unscheduled

---

## Problem Statement

When running the volatility screener with correlation filtering enabled, the system fetches **120 days** of historical candle data for each symbol on every cache expiration, even though only 1-3 new days of data are needed.

**Current Behavior:**
- Morning screener run: Cache expired (8hr TTL) → re-fetch all 120 days
- Result: 4-5 seconds for 150-symbol watchlist

**Desired Behavior:**
- Fetch only new candles since last update (delta/incremental pull)
- Result: 0.8-1.2 seconds for same workload

**Why 120 Days?**
Required for HV90 (90-day historical volatility) calculation used in VRP Structural metric.

---

## Proposed Solution

Implement **append-only delta fetching** with automatic fallback to full fetch.

### High-Level Design

1. **New Cache Entry:** `returns_meta_{symbol}` with:
   - `last_update`: Timestamp of most recent candle
   - `candles`: Array of CandleData objects
   - `returns`: Calculated log returns
   - `window_days`: Rolling window size (120)

2. **Fetch Logic:**
   ```
   if cache exists and age < window_days:
       fetch only (now - last_update) days
       append to existing candles
       trim to 120-day window
       recalculate returns
   else:
       full fetch (120 days)
   ```

3. **Fallback:** Any error → transparent fallback to full fetch

### Files to Modify

- `src/variance/market_data/dxlink_client.py` - Add `from_time` support (already exists)
- `src/variance/market_data/dxlink_hv_provider.py` - Add delta fetch method
- `src/variance/market_data/cache.py` - Add `returns_meta` helpers
- `src/variance/market_data/pure_tastytrade_provider.py` - Use delta fetch
- `src/variance/market_data/settings.py` - Add TTL for `returns_meta`

---

## Expected Impact

### Performance Gains

**150-symbol watchlist:**

| Scenario | Current | With Delta | Improvement |
|----------|---------|------------|-------------|
| Cold cache (first run) | 6-8s | 6-8s | 0% (same) |
| Daily refresh (next day) | 4-5s | **0.8-1.2s** | **75-80%** |
| Weekly refresh (7 days stale) | 4-5s | **1.5-2s** | **60-65%** |
| Candles fetched (daily) | 18,000 | **750** | **95% reduction** |

### Real-World Benefit

**Typical Usage:**
- Morning screener: **3-4s saved per day**
- Annual time saved: ~18-24 hours (250 trading days)

---

## Trade-offs

### Pros ✅
- 75-80% faster daily screening runs
- 95% reduction in DXLink data transfer
- Transparent fallback (no user-facing failures)
- Maintains full 120-day window for HV90

### Cons ❌
- Adds 150-200 lines of code
- Increased testing surface (cache states, holidays, splits)
- Additional cache schema to maintain
- Complexity in handling corporate actions

---

## Why This is Deferred (Not Rejected)

1. **Current performance is acceptable:** 4-5s for 150 symbols is reasonable for daily use
2. **Simple alternatives exist:** Increase cache TTL to 24hr → 80% of benefit, 0 LOC
3. **Diminishing returns:** Only optimizes daily refresh case (not intraday)
4. **Premature optimization:** Watchlist size may not grow beyond 200 symbols

---

## When to Implement

**Triggers for prioritization:**

- [ ] Watchlist grows beyond **500 symbols** (>10s screening time)
- [ ] User complaints about screening speed
- [ ] CI/CD integration where every second matters
- [ ] Multi-portfolio users running screener 10+ times/day

**Leading Indicators:**
- Screening time consistently >8s
- Cache hit rate <50%
- Users manually increasing cache TTL in config

---

## Simple Alternatives to Try First

### 1. Increase Cache TTL (Zero Code Change)

```python
# src/variance/market_data/settings.py
AFTER_HOURS_TTL = {
    "market_data": 86400,  # 24 hours (currently 8 hours)
}
```

**Impact:** Morning screener uses yesterday's data (acceptable for screening)
**Benefit:** 80% of delta fetch performance gain with 0 lines of code

### 2. Increase DXLink Batch Size (Config Change)

Fetch more symbols in parallel to amortize WebSocket overhead.

**Impact:** 20-30% speedup with config tuning
**Trade-off:** Higher DXLink API load

---

## Detailed Analysis

See: [`docs/research/delta-fetching-optimization.md`](../research/delta-fetching-optimization.md)

**Contains:**
- Full implementation design with code samples
- Edge case analysis (holidays, splits, cache corruption)
- Benchmark scenarios and calculations
- Risk mitigation strategies
- Testing requirements

---

## Acceptance Criteria

If/when implemented:

- [ ] Delta fetch reduces daily screening time by >60%
- [ ] Fallback to full fetch on any error (zero user-facing failures)
- [ ] Handles market holidays gracefully (no date alignment issues)
- [ ] Detects corporate actions and triggers full fetch
- [ ] Unit tests cover: cold cache, 1-day stale, 7-day stale, holidays, splits
- [ ] Integration test validates 120-day rolling window maintained
- [ ] Performance metrics logged (cache hit rate, delta fetch savings)
- [ ] Documentation updated with new cache schema

---

## Related

- RFC 013: Correlation Guard (requires returns data)
- Commit `ff9932f`: Fixed correlation filter to enable returns fetching
- Issue #XXX: Performance benchmarking (if exists)

---

## Comments

> **Note:** This is a **quality-of-life optimization**, not a critical fix. Current performance is acceptable for typical usage. Prioritize only if screening becomes a daily pain point or watchlist scales significantly.

> **Recommendation:** Try increasing cache TTL to 24 hours first (simple alternative). Only implement delta fetching if that proves insufficient.
