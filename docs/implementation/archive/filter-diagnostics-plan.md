# Filter Diagnostics Implementation Plan

## Context
User wants to understand filter behavior in vol screener. Currently only have aggregate counts (18 low VRP, 40 low IVP) but unclear:
- Which symbols failed which filters
- Sequential waterfall effect (filters applied in order)
- Exact values causing rejection

## Three Diagnostic Levels

### Level 1: Filter Waterfall (Sequential Tracking)
**File:** `src/variance/screening/steps/filter.py`

**Changes:**
1. Add `waterfall: list[dict]` to `ScreeningContext` dataclass
2. In `apply_specifications()`, after each spec check, record:
   ```python
   waterfall.append({
       "step": "VRP Structural",
       "remaining": len(candidates),
       "rejected_this_step": rejected_count
   })
   ```
3. Return waterfall in report metadata

**Implementation:**
- Track remaining count after each filter in sequence
- Order: DataIntegrity → VrpStructural → VolTrap → VolMomentum → RetailEfficiency → IVPercentile → Yield → Liquidity → VrpTactical → Correlation

### Level 2: Per-Symbol Rejection Reasons (--debug flag)
**Files:**
- `src/variance/vol_screener.py` (add CLI arg)
- `src/variance/screening/steps/filter.py` (track rejections)

**Changes:**
1. Add `--debug` CLI argument to vol_screener.py
2. Add `rejections: dict[str, str]` to ScreeningContext
3. In filter loop, when spec fails, record:
   ```python
   if not spec.is_satisfied_by(metrics_dict):
       rejections[symbol] = f"{spec.name}: {spec.get_reason(metrics_dict)}"
   ```
4. Add `get_reason()` method to all Specification classes showing exact values
5. Return rejections dict in report metadata (only if debug=True)

**Spec Reason Examples:**
- `VrpStructuralSpec.get_reason()`: "VRP Structural: 0.85 < 1.00"
- `IVPercentileSpec.get_reason()`: "IV Percentile: 12% < 25%"
- `RetailEfficiencySpec.get_reason()`: "Slippage: 8.2% > 5.0%"

### Level 3: Detailed Spec Logging
**Files:** All specs in `src/variance/models/market_specs.py`

**Changes:**
1. Add optional `verbose: bool` parameter to each Specification class
2. In `is_satisfied_by()`, add debug logging:
   ```python
   if self.verbose:
       logger.debug(f"{self.name} evaluating {data['symbol']}: {value} vs {threshold} = {result}")
   ```
3. Enable via environment variable `VARIANCE_DEBUG_SPECS=1`

## Implementation Order

1. **Level 2 First** (easiest, most useful)
   - Add `--debug` flag to CLI
   - Add `rejections` dict to ScreeningContext
   - Implement `get_reason()` on all specs
   - Update report builder to include rejections

2. **Level 1 Second** (sequential tracking)
   - Add waterfall tracking in filter.py
   - Record state after each filter stage
   - Update report metadata

3. **Level 3 Last** (verbose logging)
   - Add verbose mode to specs
   - Environment variable control
   - Logger configuration

## Output Format Changes

### format_screener_output.py additions:

**Level 1 Display:**
```
FILTER WATERFALL
─────────────────────────────────────
  1. Loaded:                     50 symbols
  2. After Data Integrity:       49 (-1)
  3. After VRP Structural:       31 (-18)
  4. After Vol Momentum:         28 (-3)
  ...
  FINAL: Candidates:              2
```

**Level 2 Display (--debug only):**
```
REJECTION DETAILS
─────────────────────────────────────
AAPL:  Low IV Percentile (12% < 25%)
TSLA:  Retail Inefficient (Slippage: 8.2% > 5%)
NVDA:  Low Yield (2.1% < 3.5%)
```

## Testing
```bash
# Test Level 1 (always on)
./screen 50

# Test Level 2 (debug mode)
./screen 50 --debug

# Test Level 3 (verbose specs)
VARIANCE_DEBUG_SPECS=1 ./screen 50
```

## Files to Modify
1. `src/variance/vol_screener.py` - Add --debug CLI arg
2. `src/variance/screening/pipeline.py` - Pass debug flag to context
3. `src/variance/screening/steps/filter.py` - Track waterfall + rejections
4. `src/variance/models/market_specs.py` - Add get_reason() to all specs
5. `scripts/format_screener_output.py` - Display new diagnostics

## Estimated Effort
- Level 2: 2-3 hours (CLI + rejection tracking + reason methods)
- Level 1: 1-2 hours (waterfall tracking)
- Level 3: 1 hour (verbose logging)
- Testing: 1 hour
**Total: 5-7 hours**
