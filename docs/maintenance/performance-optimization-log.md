# Performance Optimization Log

This document tracks performance bottlenecks, optimizations, and future opportunities for the Variance volatility screener.

## Benchmark Methodology

Run benchmarks with the `VARIANCE_BENCHMARK` environment variable:

```bash
VARIANCE_BENCHMARK=1 ./screen 50 --json 2>&1 | grep -A 10 "MARKET DATA FETCH BREAKDOWN"
VARIANCE_BENCHMARK=1 ./screen 100 --json 2>&1 | grep -A 10 "MARKET DATA FETCH BREAKDOWN"
```

This enables detailed timing breakdowns in:
- `src/variance/screening/pipeline.py` - Overall pipeline stages
- `src/variance/market_data/pure_tastytrade_provider.py` - Market data fetch breakdown

## Optimization History

### 2026-01-01: Parallel Option Chain Fetching ✅ COMPLETED

**Problem:** Option chain fetches were sequential, taking 342ms per symbol (12s total for 35 symbols)

**Solution:** Implemented async parallel fetching using `asyncio` + `httpx.AsyncClient`
- File: `src/variance/tastytrade_client.py`
- Method: `_get_option_chains_async()` with semaphore rate limiting
- Concurrency: 10 concurrent requests (configurable via `config/runtime_config.json`)

**Results:**
```
BEFORE (Sequential):
- Option Chains: 11,976ms for 35 symbols (342ms avg)
- Total Runtime: 29,945ms for 50 symbols (598.9ms/symbol)

AFTER (Parallel):
- Option Chains: 928ms for 35 symbols (25ms avg)  ← 12.9x speedup
- Total Runtime: 19,086ms for 50 symbols (381.7ms/symbol)  ← 1.6x speedup
```

**Impact:**
- 50 symbols: 29.9s → 19.1s (36% reduction)
- 100 symbols: ~60s → 20.6s (66% reduction)
- 500 symbols (projected): 324s → 103s (3.1x faster)

**Implementation Details:**
- `max_concurrent_option_chains: 10` in `config/runtime_config.json`
- Token refresh protected by `asyncio.Lock()` to prevent race conditions
- Error handling: 404 skipped, 429 retried with backoff, partial failures tolerated
- Backward compatible - no breaking API changes

## Current Performance Metrics (as of 2026-01-01)

### 50 Symbols
```
Total: 19,086ms (381.7ms/symbol)
--------------------------------------------------------------------------------
  DXLink Batch (23 symbols)                   15,570ms  ( 81.6%)  ← PRIMARY BOTTLENECK
  Option Quotes                                2,186ms  ( 11.5%)  ← OPTIMIZED
  TT Metrics API                                 683ms  (  3.6%)
  TT Prices API                                  639ms  (  3.3%)
  Merge & Cache                                    8ms  (  0.0%)
```

### 100 Symbols
```
Total: 20,624ms (206.2ms/symbol)
--------------------------------------------------------------------------------
  DXLink Batch (35 symbols)                   15,513ms  ( 75.2%)  ← PRIMARY BOTTLENECK
  Option Quotes                                3,926ms  ( 19.0%)  ← OPTIMIZED
  TT Metrics API                                 687ms  (  3.3%)
  TT Prices API                                  479ms  (  2.3%)
  Merge & Cache                                   19ms  (  0.1%)
```

## Remaining Bottlenecks

### 1. DXLink Batch (Historical Volatility for Futures) - PRIMARY

**Current State:**
- 15.5s for 23-35 symbols (81.6% of 50-symbol runtime, 75.2% of 100-symbol runtime)
- ~443-673ms per symbol
- Used for futures/indexes that lack historical data from Tastytrade

**Details:**
- File: `src/variance/market_data/dxlink_hv_provider.py`
- Uses DXLink WebSocket connection via `tastytrade-dxlink` library
- Fetches candle data, then calculates HV20/HV30/HV252 locally
- Currently batched but not parallelized

**Why It's Slow:**
- WebSocket batch operation (not simple HTTP like option chains)
- Requires candle data fetch + local HV calculation
- Limited by DXLink API response time

**Optimization Opportunities:**
1. **Parallel batches** - Split symbols into multiple concurrent WebSocket batches
2. **Local caching** - Cache HV calculations (low volatility changes slowly)
3. **Selective fetching** - Only fetch HV for symbols likely to pass filters
4. **Pre-filtering** - Use IV Percentile filter first (cheap), then fetch HV only for survivors

**Estimated Impact:**
- Parallelization (3 concurrent batches): ~5x speedup → 3.1s instead of 15.5s
- With caching: Could reduce by 50-80% for repeated scans
- Combined with pre-filtering: Could skip 70% of HV fetches

**Complexity:** HIGH (WebSocket vs HTTP, requires tastytrade-dxlink library changes)

### 2. TT Metrics API (IV, IVR, IVP, Liquidity)

**Current State:**
- 683-687ms for 50-100 symbols (~3.3% of runtime)
- Already batched (single API call for all symbols)

**Optimization Opportunities:**
- Minimal - already very fast and well-optimized
- Could cache for repeated scans (15min TTL)

**Estimated Impact:** Low priority (already <1s)

### 3. TT Prices API (Bid/Ask/Last)

**Current State:**
- 479-639ms for 50-100 symbols (~2.3% of runtime)
- Already batched (single API call for all symbols)

**Optimization Opportunities:**
- Minimal - already very fast
- Could cache for 1-5 minutes during market hours

**Estimated Impact:** Low priority (already <1s)

## Future Optimization Roadmap

### High Priority
1. **DXLink Parallel Batching** - Parallelize HV fetches for futures (potential 5x speedup)
2. **HV Caching** - Cache historical volatility calculations (slow-moving data)

### Medium Priority
3. **Pre-filtering Pipeline** - Fetch cheap metrics first (IV, price), filter, then fetch expensive data (HV, option chains) only for survivors
4. **Smart Watchlist Segmentation** - Separate equity vs futures symbols, fetch in parallel

### Low Priority
5. **Metrics/Prices Caching** - Cache TT API responses for 1-15 minutes
6. **Connection Pooling** - Reuse HTTP connections across scans (may already be optimized by httpx)

## Projected Performance with Full Optimization

**500 Symbols (Current):**
```
Total: ~103 seconds (206ms/symbol)
- DXLink: ~75s (75%)
- Option Quotes: ~20s (19%)
- Other: ~8s (6%)
```

**500 Symbols (Fully Optimized):**
```
Total: ~30 seconds (60ms/symbol)
- DXLink (parallel + cached): ~15s (50%)
- Option Quotes (cached): ~10s (33%)
- Other: ~5s (17%)
```

**Estimated Improvement:** 103s → 30s (3.4x speedup, 71% reduction)

## Configuration

Performance-related settings in `config/runtime_config.json`:

```json
{
  "tastytrade": {
    "max_concurrent_option_chains": 10,     // Parallel option chain fetches
    "batch_size": 50,                        // TT API batch size
    "cache_ttl_seconds": 900                 // Cache TTL (15 min)
  }
}
```

## Tools & Scripts

- `src/variance/screening/benchmark.py` - Pipeline benchmark infrastructure
- `VARIANCE_BENCHMARK=1` env var - Enable detailed timing
- `scripts/format_screener_output.py` - Human-readable benchmark output

## Notes

- Option chain optimization (2026-01-01) was the "low-hanging fruit" - simple HTTP parallelization
- DXLink optimization is more complex (WebSocket protocol, external library dependency)
- Consider DXLink optimization only if scanning 200+ symbols regularly
- For <100 symbol watchlists, current performance is acceptable (20-30s total)
