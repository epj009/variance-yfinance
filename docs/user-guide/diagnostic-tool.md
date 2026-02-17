# Symbol Diagnostic Tool

**Script**: `scripts/diagnose_symbol.py`
**Purpose**: Troubleshoot why symbols pass or fail screening filters

---

## Quick Start

```bash
# Diagnose single symbol
./scripts/diagnose_symbol.py AAPL

# Diagnose futures
./scripts/diagnose_symbol.py /ES /CL /ZN

# Check if held position is scalable
./scripts/diagnose_symbol.py --held TSLA

# JSON output
./scripts/diagnose_symbol.py --json NVDA > output.json

# Multiple symbols
./scripts/diagnose_symbol.py AAPL MSFT NVDA SPY
```

---

## Use Cases

### 1. "Why isn't my symbol showing up?"

**Problem**: You expect AAPL to pass filters but it doesn't appear in the screener.

**Solution**:
```bash
./scripts/diagnose_symbol.py AAPL
```

**Output**:
```
================================================================================
DIAGNOSING: AAPL
================================================================================

📊 Key Metrics:
   price: 150.0
   vrp_structural: 0.95
   iv_percentile: 15

🔍 Filter Results:
✅ DataIntegrity: True
❌ VrpStructural: False
   VRP 0.95 <= 1.1
❌ IVPercentile: False
   IVP 15 < 20.0
✅ VolatilityMomentum: True
   ...

================================================================================
❌ RESULT: AAPL REJECTED by: VrpStructural, IVPercentile
================================================================================
```

**Diagnosis**: VRP too low (0.95 < 1.10) and IV Percentile too low (15 < 20).

---

### 2. "Why isn't my held position showing up?"

**Problem**: You hold /ZN and it has VRP 1.79 but doesn't appear in the screener.

**Solution**:
```bash
./scripts/diagnose_symbol.py --held /ZN
```

**Output**:
```
================================================================================
DIAGNOSING: /ZN (HELD POSITION)
================================================================================

🔍 Filter Results:
✅ VrpStructural: True
   VRP 1.79 > 1.1
✅ IVPercentile: True
   IVP 35.2 >= 20
❌ ScalableGate: False
   VTM 0.000 < 1.35 OR Divergence 0.558 < 1.1

================================================================================
❌ RESULT: /ZN REJECTED by: ScalableGate
================================================================================
```

**Diagnosis**: Held positions only show if VRP Tactical Markup >= 1.35 (scalable surge). Your position passes all normal filters but doesn't meet the scalability threshold.

**Solution**: Remove from `--held-symbols` to see it in the screener.

---

### 3. "Why aren't futures showing up?"

**Problem**: Futures (/ES, /CL) never appear in results.

**Solution**:
```bash
./scripts/diagnose_symbol.py /ES /CL /ZN
```

**Output**:
```
DIAGNOSING: /ES
❌ RESULT: /ES REJECTED by: VrpStructural
   VRP 0.57 <= 1.1

DIAGNOSING: /CL
❌ RESULT: /CL REJECTED by: VrpStructural, RetailEfficiency
   VRP 0.96 <= 1.1
   Price $58.35 (slippage 5.21% > 5%)

DIAGNOSING: /ZN
✅ RESULT: /ZN PASSES all filters
```

**Diagnosis**: Most futures have low VRP (< 1.10) during calm markets. Only /ZN passes.

---

### 4. "Compare multiple symbols"

**Problem**: Want to understand which candidates are closest to passing.

**Solution**:
```bash
./scripts/diagnose_symbol.py AAPL MSFT NVDA TSLA
```

**Output**:
```
================================================================================
📊 SUMMARY: 2/4 symbols passed all filters
================================================================================
```

---

## Output Modes

### Human-Readable (Default)

Shows clear pass/fail for each filter with explanations:

```
🔍 Filter Results:
✅ VrpStructural: True
   VRP 1.22 > 1.1
❌ IVPercentile: False
   IVP 15 < 20.0
```

### JSON Mode (`--json`)

Machine-readable output for automation:

```json
{
  "symbols": [
    {
      "symbol": "AAPL",
      "status": "REJECT",
      "metrics": {
        "price": 150.0,
        "vrp_structural": 0.95,
        "iv_percentile": 15
      },
      "filters": {
        "VrpStructural": {
          "passed": false,
          "threshold": 1.1,
          "value": 0.95,
          "reason": "VRP 0.95 <= 1.1"
        },
        ...
      },
      "failed_filters": ["VrpStructural", "IVPercentile"]
    }
  ]
}
```

---

## Filter Checks

The diagnostic tests these filters in order:

| # | Filter | What It Checks |
|---|--------|----------------|
| 1 | **DataIntegrity** | Data errors/warnings |
| 2 | **VrpStructural** | VRP > 1.10 |
| 3 | **VolatilityTrap** | HV Rank >= 15 (universal) |
| 4 | **VolatilityMomentum** | HV30/HV90 (VTR) >= 0.85 |
| 5 | **RetailEfficiency** | Price >= $25, Slippage <= 5% |
| 6 | **IVPercentile** | IV Percentile >= 20 |
| 7 | **Liquidity** | Tastytrade rating >= 4 |
| 8 | **ScalableGate** | VTM >= 1.35 (only for `--held`) |

---

## Common Scenarios

### Scenario: Symbol passes filters but doesn't appear

**Possible Causes**:
1. **Correlation Filter** (not shown in diagnostic - only applies when `--held-symbols` provided)
2. **Asset Class Filter** (check `--include-asset-classes` / `--exclude-asset-classes`)
3. **Sector Exclusion** (check `--exclude-sectors`)

**Solution**: Run full screener with `--debug` flag for complete diagnostics.

---

### Scenario: Futures rejected by IV Percentile filter

**Explanation**: Tastytrade provides IV Percentile for both equities and futures. Futures are subject to the same IV% threshold as equities.

**If Rejected**: The futures contract has low IV relative to its historical range. This is normal market behavior - not all futures will pass at all times.

---

### Scenario: "Missing HV30/HV90 data (pass-through)"

**Explanation**: Tastytrade doesn't provide HV30/HV90 for some symbols. VolatilityMomentumSpec allows them to pass.

**Impact**: These symbols skip the compression check.

---

### Scenario: Held position shows different results than new candidate

**Explanation**: Held positions have an additional `ScalableGate` filter that only passes if:
- VRP Tactical Markup >= 1.35 (absolute surge)
- OR Divergence >= 1.10 (relative surge)

**Solution**: Use `--held` flag to see the ScalableGate check.

---

## Comparison with Screener

**Diagnostic Tool**:
- ✅ Shows ALL filter results (pass + fail)
- ✅ Explains WHY each filter passed/failed
- ✅ Works for single symbols or small batches
- ❌ Doesn't apply correlation filter
- ❌ Doesn't apply sector/asset class filters

**Screener** (`./variance --tui`):
- ✅ Processes entire watchlist (300+ symbols)
- ✅ Applies ALL filters including correlation
- ✅ Shows only passing candidates
- ❌ Doesn't explain why symbols failed

**When to Use Each**:
- **Diagnostic**: Troubleshooting specific symbols
- **Screener**: Finding all candidates from watchlist

---

## Automation Examples

### Save results to file
```bash
./scripts/diagnose_symbol.py AAPL MSFT NVDA > report.txt
```

### Process JSON output
```bash
./scripts/diagnose_symbol.py --json AAPL | jq '.symbols[0].failed_filters'
# Output: ["VrpStructural", "IVPercentile"]
```

### Batch check watchlist subset
```bash
while read symbol; do
  ./scripts/diagnose_symbol.py "$symbol"
done < my_symbols.txt
```

### Filter only passing symbols
```bash
./scripts/diagnose_symbol.py --json /ES /CL /ZN /NG | \
  jq '.symbols[] | select(.status == "PASS") | .symbol'
# Output: "/ZN"
```

---

## Flags Reference

| Flag | Description | Example |
|------|-------------|---------|
| (none) | Human-readable output | `./scripts/diagnose_symbol.py AAPL` |
| `--held` | Treat as held position (check scalability) | `./scripts/diagnose_symbol.py --held TSLA` |
| `--json` | JSON output for automation | `./scripts/diagnose_symbol.py --json NVDA` |

---

## Limitations

1. **No Correlation Check**: Doesn't test `CorrelationSpec` (requires portfolio context)
2. **Simplified Liquidity**: Shows Tastytrade rating only, not full fallback logic
3. **No Sector/Asset Class Filters**: Doesn't apply command-line filters like `--exclude-sectors`

**For complete filtering**: Use the main screener with `--debug` flag.

---

## Troubleshooting

### Error: "ModuleNotFoundError"
**Solution**: Run from project root:
```bash
cd /path/to/variance-yfinance
./venv/bin/python3 scripts/diagnose_symbol.py AAPL
```

### Error: "FETCH ERROR: market_closed_no_cache"
**Cause**: Market is closed and symbol has no cached data.
**Solution**: Run during market hours or after a successful screener run (creates cache).

### Output shows "Missing" for many metrics
**Cause**: Christmas/holiday data quality issues.
**Solution**: Run during normal market hours.

---

## Related Documentation

- **Filter Rules**: `docs/user-guide/filtering-rules.md` - Complete filter documentation
- **Config Guide**: `docs/user-guide/config-guide.md` - Threshold configuration
- **Screener Usage**: `./variance --help` - Main CLI usage

---

## Version History

- **1.0.0** (2025-12-25): Initial diagnostic tool
  - All 8 filters tested
  - `--held` flag for scalability check
  - `--json` output mode
