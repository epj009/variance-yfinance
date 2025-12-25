# ADR 0008: Multi-Provider Architecture with Composite Pattern

## Status
Accepted

## Context
Variance initially relied exclusively on yfinance for all market data (price, IV, HV, earnings). However, yfinance has several limitations:

1. **IV Quality**: Computed from option chains using complex normalization heuristics, prone to scale errors (decimal vs percent)
2. **Missing Metrics**: No native IVR (IV Rank), IVP (IV Percentile), or liquidity ratings
3. **Limited HV Windows**: Only HV20/HV252 available via computed historical prices, not HV30/HV90
4. **Reliability**: Rate limiting and occasional API failures during batch fetches

Tastytrade offers institutional-grade market metrics via `/market-metrics` endpoint:
- Native IV, IVR, IVP from market-maker data
- HV30, HV90 (30-day and 90-day historical volatility)
- Liquidity rating (1-5 scale) and liquidity value
- Earnings dates and correlation metrics

However, Tastytrade's `/market-metrics` endpoint does **not include price or returns data** (quotes require DXLink streaming entitlements). This creates a need for **multi-source data composition**.

## Decision
We will implement a **Composite Provider Pattern** using the existing `IMarketDataProvider` interface:

### Architecture Choice: Option A (Non-Overlapping Field Composition)

```
TastytradeProvider (implements IMarketDataProvider):
  ├─ Tastytrade API: iv, iv_rank, iv_percentile, hv30, hv90,
  │                  liquidity_rating, liquidity_value, earnings_date
  └─ YFinanceProvider (internal): price, returns, sector

  Returns: Merged MarketData with data_source="composite"
```

**Field Ownership (No Overlaps)**:
- **Tastytrade owns**: All volatility metrics (IV, HV, IVR, IVP), liquidity data
- **yfinance owns**: Price, returns, sector classification
- **No conflicts**: Each provider contributes disjoint fields

### Alternatives Considered

**Option B: Independent Providers + Config Swap**
```
runtime_config.json: { "provider": "tastytrade" } OR { "provider": "yfinance" }
```
- **Rejected**: Cannot mix sources (Tastytrade lacks price, yfinance lacks IVR/IVP/HV30/HV90)

**Option C: Multi-Provider Orchestrator with Field-Level Routing**
```
CompositeProvider:
  - Routes each field to provider based on config
  - Merge logic handles conflicts per field
```
- **Rejected**: Over-engineered for current needs, introduces merge conflict complexity
- **Future consideration**: If adding Interactive Brokers or TD Ameritrade with overlapping fields

### Fallback Strategy
If Tastytrade fails (auth error, rate limit, server error):
1. Log warning with failure reason
2. Fall back to yfinance-only data for entire batch
3. Set `warning: "tastytrade_fallback"` on all returned MarketData
4. Compute VRP using yfinance HV20/HV252 (legacy formulas)

### Provider Priority (Future Extension)
When adding new brokers (e.g., Interactive Brokers):
```
runtime_config.json: {
  "provider_priority": ["tastytrade", "interactive_brokers", "yfinance"]
}
```
Factory tries providers in order until success (no merge conflicts, only failover).

## Consequences

### Pros
1. **Clean Separation**: Each provider owns disjoint fields, zero merge conflicts
2. **Extensibility**: New brokers can be added by implementing `IMarketDataProvider`
3. **Graceful Degradation**: System continues working if Tastytrade unavailable
4. **Field-Level Quality**: Use best source for each data type (Tastytrade for vol, yfinance for price)
5. **Runtime Swappable**: Can A/B test providers via config without code changes
6. **Single Responsibility**: Each provider does one thing well

### Cons
1. **Internal Coupling**: TastytradeProvider internally depends on YFinanceProvider for price/returns
   - **Mitigation**: Dependency injection allows mocking/testing
2. **Dual API Calls**: Each symbol requires two API calls (Tastytrade + yfinance)
   - **Mitigation**: Parallel execution via ThreadPoolExecutor, caching reduces redundant calls
3. **Config Complexity**: More settings in `runtime_config.json` (Tastytrade section)
   - **Mitigation**: Sensible defaults, env var validation on startup

### Migration Impact
- **VRP Formulas Change**: `IV/HV252` → `IV/HV90` (structural), `IV/HV20` → `IV/HV30` (tactical)
- **Threshold Tuning Required**: New HV windows require recalibrating `vrp_structural_threshold` in `trading_rules.json`
- **New Fields Available**: Screeners can now use `iv_rank`, `iv_percentile`, `liquidity_rating`
- **Backward Compatibility**: Legacy HV20/HV252 still populated for fallback scenarios

## References
- Implementation Plan: `docs/implementation/tastytrade_swap_plan.md`
- Technical Spec: Architect agent output (Phase 1)
- Related ADRs: ADR-0002 (Strategy Pattern), ADR-0005 (Execution Isolation)
