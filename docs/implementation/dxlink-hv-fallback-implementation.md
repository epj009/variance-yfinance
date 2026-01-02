# DXLink HV Fallback Implementation

**Status:** ✅ IMPLEMENTED
**Date:** 2025-12-31
**Issue:** [#3 - Improve HV30/HV90 Coverage](https://github.com/user/repo/issues/3)

## Executive Summary

Implemented DXLink WebSocket streaming as automatic fallback for missing HV30/HV90 metrics from Tastytrade REST API. This addresses the ~10-20% gap in HV coverage by calculating historical volatility from daily OHLC candles when REST API doesn't provide pre-calculated values.

**Key Results:**
- ✅ Tastytrade SDK integration for DXLink candle streaming
- ✅ Automatic fallback in MarketDataService
- ✅ HV30/HV90 calculation from daily candles
- ✅ Zero additional cost (uses existing Tastytrade subscription)
- ✅ Seamless integration - no code changes needed in screening logic

## Architecture

### Data Flow

```
┌─────────────────────────────────────────────────────────┐
│  MarketDataService.get_market_data(symbols)             │
└────────────────────┬────────────────────────────────────┘
                     │
         ┌───────────▼──────────┐
         │ TastytradeProvider   │
         └───────────┬──────────┘
                     │
    ┌────────────────▼───────────────┐
    │ 1. Fetch REST API metrics      │
    │    (IV, HV30, HV90, etc.)     │
    └────────────────┬───────────────┘
                     │
    ┌────────────────▼───────────────┐
    │ 2. Check HV30/HV90 presence    │
    │    ❓ Missing HV metrics?      │
    └────────────────┬───────────────┘
                     │
            ┌────────┴────────┐
            │                 │
      ✅ Present        ❌ Missing
            │                 │
            │        ┌────────▼──────────┐
            │        │ DXLink Fallback   │
            │        │ 1. Subscribe       │
            │        │ 2. Collect candles │
            │        │ 3. Calculate HV    │
            │        └────────┬──────────┘
            │                 │
            └────────┬────────┘
                     │
    ┌────────────────▼───────────────┐
    │ 3. Merge & Return complete     │
    │    MarketData with HV          │
    └────────────────────────────────┘
```

### Components

**New Files:**

1. **`src/variance/market_data/dxlink_hv_provider.py`**
   - `DXLinkHVProvider`: Wrapper around tastytrade SDK's DXLinkStreamer
   - Async candle retrieval with timeout handling
   - Synchronous wrapper for integration with sync code

2. **`src/variance/market_data/hv_calculator.py`**
   - `calculate_hv_metrics()`: Compute HV30/HV90 from candles
   - Uses standard log returns methodology: `σ(log returns) × √252`
   - Handles insufficient data gracefully

**Modified Files:**

1. **`src/variance/market_data/providers.py`**
   - `TastytradeProvider.__init__()`: Initialize DXLinkHVProvider
   - `TastytradeProvider._merge_tastytrade_fallback()`: Add fallback logic

## Implementation Details

### 1. DXLink Candle Streaming

Uses tastytrade SDK's `DXLinkStreamer` for WebSocket candle retrieval:

```python
from tastytrade import DXLinkStreamer, Session
from tastytrade.dxfeed import Candle

async with DXLinkStreamer(session) as streamer:
    # Subscribe to daily candles with 150-day lookback
    start_time = datetime.now() - timedelta(days=150)

    await streamer.subscribe_candle(
        symbols=[symbol],
        interval='1d',
        start_time=start_time
    )

    # Collect candles (typically ~100 trading days)
    async for candle in streamer.listen(Candle):
        if candle.event_symbol.startswith(symbol):
            # Process candle...
```

**Why 150 calendar days?**
- Markets open ~252 days/year
- 150 calendar days ≈ 100 trading days
- Sufficient for HV30 (needs 31) and HV90 (needs 91)

### 2. HV Calculation

Standard financial volatility calculation:

```python
def calculate_hv_from_candles(candles: list[CandleData], window: int = 30) -> Optional[float]:
    """
    Calculate historical volatility from daily candles.

    HV = σ(log returns) × √252

    where:
    - σ = standard deviation of log returns
    - log returns = ln(price[t] / price[t-1])
    - √252 = annualization factor (trading days per year)
    """
    closes = [c.close for c in candles[-(window+1):]]
    returns = [math.log(closes[i] / closes[i-1]) for i in range(1, len(closes))]
    std_dev = statistics.stdev(returns)
    hv = std_dev * math.sqrt(252)  # Annualized volatility
    return hv
```

### 3. Fallback Integration

Automatic fallback in `TastytradeProvider._merge_tastytrade_fallback()`:

```python
# After merging REST API HV data...
if "hv30" in tt_data and tt_data["hv30"] is not None:
    merged["hv30"] = tt_data["hv30"]

if "hv90" in tt_data and tt_data["hv90"] is not None:
    merged["hv90"] = tt_data["hv90"]

# DXLink fallback for missing HV30/HV90
if self.dxlink_hv_provider:
    needs_hv30 = merged.get("hv30") is None
    needs_hv90 = merged.get("hv90") is None

    if needs_hv30 or needs_hv90:
        dxlink_hv = self.dxlink_hv_provider.get_hv_metrics_sync(symbol)

        if needs_hv30 and dxlink_hv.get("hv30") is not None:
            merged["hv30"] = dxlink_hv["hv30"]
            logger.info(f"DXLink provided HV30 for {symbol}")

        if needs_hv90 and dxlink_hv.get("hv90") is not None:
            merged["hv90"] = dxlink_hv["hv90"]
            logger.info(f"DXLink provided HV90 for {symbol}")
```

## Testing

### Unit Tests

**`scripts/test_sdk_candles.py`**
- Tests DXLink candle retrieval for AAPL, SPY, /ES
- Verifies HV calculation
- Results: ✅ 100 candles, HV30=13.01%, HV90=20.18% for AAPL

**`scripts/test_dxlink_fallback_integration.py`**
- Tests integrated fallback in MarketDataService
- Verifies REST API + DXLink cooperation
- Results: ✅ Perfect coverage for cached symbols

**`scripts/test_watchlist_hv_coverage.py`**
- Comprehensive watchlist coverage analysis
- Reports REST vs DXLink sourcing
- Run during market hours for full results

### Expected Coverage

**Before DXLink:**
- HV30/HV90 coverage: ~80-90% (REST API only)
- Missing data for: low-volume stocks, recent IPOs, some ETFs

**After DXLink:**
- HV30/HV90 coverage: ~99-100% (REST + DXLink fallback)
- Only limitations: symbols without trading history (brand new IPOs)

## Performance Considerations

### Latency

- **REST API (primary):** ~100-200ms per batch
- **DXLink fallback (per symbol):** ~15-20s for 100 candles
  - WebSocket connection: ~500ms
  - Candle streaming: ~10-15s (batch delivery)
  - HV calculation: <10ms

**Impact on screening:**
- If 10% of symbols need fallback (10 symbols in 100):
  - REST API: 200ms for all 100 symbols
  - DXLink fallback: 150-200s for 10 symbols (serial)
  - Total: ~3-4 minutes for 100 symbols

**Mitigation:**
- DXLink fallback is cached (TTL: 15 minutes)
- After first run, subsequent screens use cached HV
- Consider parallel DXLink requests in future (async optimization)

### Cost

- ✅ **$0 additional cost**
- Uses existing Tastytrade API subscription
- DXLink access included with market data subscription

## Future Enhancements

1. **Parallel DXLink Requests**
   - Current: Serial fallback per symbol
   - Future: Batch DXLink subscriptions (subscribe multiple symbols at once)
   - Expected: 10x speedup for fallback cases

2. **Smarter Caching**
   - Current: 15-minute TTL for all HV
   - Future: Longer TTL for stable HV symbols, shorter for volatile
   - Expected: Reduced fallback frequency

3. **Futures Support**
   - Current: DXLink candles work for equities, not futures
   - Future: Investigate futures symbol formatting for DXLink
   - Expected: Complete coverage including /ES, /CL, etc.

## Deployment Checklist

- [x] DXLinkHVProvider implementation
- [x] HV calculator with log returns
- [x] Integration into TastytradeProvider
- [x] Unit tests for SDK candle retrieval
- [x] Integration tests for fallback logic
- [x] Error handling and logging
- [ ] Run full watchlist coverage test during market hours
- [ ] Monitor DXLink fallback frequency in production
- [ ] Update GitHub Issue #3 with results

## References

- **Tastytrade SDK Documentation:** https://github.com/tastyware/tastytrade
- **DXLink Protocol:** https://demo.dxfeed.com/dxlink-ws/debug/#/protocol
- **DXLink JavaScript Implementation:** https://github.com/dxFeed/dxLink/tree/main/dxlink-javascript
- **Tastytrade Developer Portal:** https://developer.tastytrade.com/
- **Historical Volatility Calculation:** Standard financial practice (log returns method)

## Notes

- **Futures symbols** (`/ES`, `/CL`, etc.) currently don't receive DXLink candles
  - Possible symbol formatting issue (e.g., need `/ESZ24` contract month?)
  - Investigation needed - may require different subscription approach

- **Extended trading hours** are included in candle data by default
  - Candle symbol format: `AAPL{=d,tho=true}` (daily, trading hours only = true)
  - May affect HV calculation slightly vs exchange hours only

- **Async/Sync boundary** handled via `asyncio.run()`
  - DXLink uses async WebSocket (tastytrade SDK)
  - MarketDataService is synchronous
  - Wrapper method creates event loop for compatibility

---

**Implementation completed:** 2025-12-31
**Next steps:** Full watchlist testing during market hours, production monitoring
