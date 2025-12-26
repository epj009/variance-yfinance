# Variance Screener Filtering Rules

**Last Updated**: 2025-12-25
**Version**: 2.0 (HV90/HV30 methodology)

## Overview

The Variance screener uses a **composable filter pipeline** to identify high-probability volatility trades. Each filter is a standalone rule that checks a specific criterion.

**Terminology**:
- **Filter** = A rule that accepts or rejects candidates (user-facing term)
- **Specification** = Technical implementation using the Specification Pattern (code-level)
- **Screening** = The overall process of applying filters to find candidates

**Pipeline Flow**:
```
Watchlist → Data Fetch → Filters → Enrichment → Report
                            ↓
              ┌─────────────┴─────────────┐
              │  9 Core Filters (in order) │
              └─────────────┬─────────────┘
                            ↓
                    Passing Candidates
```

---

## 🛡️ Core Filters (Applied in Order)

### 1. **DataIntegritySpec** (Always First)
**Purpose**: Reject symbols with critical data errors.

**Checks**:
- Rejects symbols with hard errors (e.g., `error: "symbol_not_found"`)
- Allows "soft warnings" like `iv_scale_corrected`, `after_hours_stale`, `tastytrade_fallback`

**Common Rejections**:
- Symbol delisted or invalid
- API timeout or rate limit
- Corrupted data

**Example**:
```
Symbol: INVALID
Error: "symbol_not_found"
Result: ❌ REJECT
```

**Config**: None (always enabled)

---

### 2. **VrpStructuralSpec** (VRP Threshold)
**Purpose**: Ensure implied volatility (IV) is elevated vs realized volatility (HV).

**Formula**:
```
VRP Structural = IV / max(HV90, hv_floor)

Where:
  IV = Implied Volatility (forward-looking)
  HV90 = Historical Volatility (90-day realized)
  hv_floor = 5.0% (prevents low-vol noise)
```

**Threshold**: `vrp_structural_threshold: 1.10`
- **1.10** = IV is 10% higher than HV90 (minimum edge)
- **1.30** = IV is 30% higher (considered "rich")
- **0.80** = IV is 20% lower (implied vol is cheap, not our edge)

**Example**:
```
Symbol: AAPL
IV: 22%
HV90: 18%
VRP: 22 / 18 = 1.22 ✅ (passes 1.10 threshold)

Symbol: SPY
IV: 12%
HV90: 15%
VRP: 12 / 15 = 0.80 ❌ (fails 1.10 threshold)
```

**Config**: `vrp_structural_threshold: 1.10`

**Philosophy**: We sell options when IV > HV (positive VRP edge).

---

### 3. **LowVolTrapSpec** (HV Floor)
**Purpose**: Reject ultra-low volatility stocks where VRP signals are unreliable.

**Formula**:
```
HV252 >= hv_floor (5.0%)
```

**Rationale**: If a stock's annual volatility is < 5%, it's likely:
- Utility stock with artificial stability
- Very low volatility with wide bid/ask spreads
- False VRP signals (e.g., VRP = 10% / 2% = 5.0, but meaningless)

**Example**:
```
Symbol: D (Dominion Energy - Utility)
HV252: 3.2%
Result: ❌ REJECT (too stable, unreliable edge)

Symbol: TSLA
HV252: 45%
Result: ✅ PASS
```

**Config**: `hv_floor_percent: 5.0`

---

### 4. **VolatilityTrapSpec** (Positional Check)
**Purpose**: Reject symbols where realized volatility is at extreme lows of its 1-year range.

**Logic**:
```
IF vrp_structural > 1.30 (rich IV):
  THEN hv_rank must be >= 15 (not at yearly lows)
```

**HV Rank**: Where current HV sits in its 1-year range:
- **0** = Lowest HV in past year
- **50** = Middle of range
- **100** = Highest HV in past year

**Rationale**: If IV is rich (>1.30) but HV is at yearly lows (<15), you're likely catching a **falling knife**. Realized vol may keep compressing, causing whipsaw.

**Example**:
```
Symbol: NFLX
VRP: 1.45 (rich)
HV Rank: 8 (near yearly lows)
Result: ❌ REJECT - Volatility trap! IV rich but HV collapsing

Symbol: NVDA
VRP: 1.35 (rich)
HV Rank: 55 (mid-range)
Result: ✅ PASS - Healthy vol environment
```

**Config**:
- `vrp_structural_rich_threshold: 1.30` (when to apply check)
- `hv_rank_trap_threshold: 15.0` (minimum HV Rank)

**Note**: Only applies when VRP > 1.30. Stocks with VRP 1.10-1.30 skip this check.

---

### 5. **VolatilityMomentumSpec** (Universal Compression Check)
**Purpose**: Reject symbols where volatility is actively collapsing, regardless of VRP level.

**Formula**:
```
HV30 / HV90 >= 0.85

Where:
  HV30 = Recent 30-day volatility
  HV90 = Medium-term 90-day volatility
  0.85 = Allows 15% contraction
```

**Rationale**: Complements VolatilityTrapSpec by checking compression across ALL VRP ranges (not just >1.30).

**Example**:
```
Symbol: XYZ
VRP: 1.15 (passes VRP threshold)
HV30: 15%
HV90: 25%
Momentum: 15 / 25 = 0.60 (40% collapse!)
Result: ❌ REJECT - Post-earnings calm, vol collapsing

Symbol: AMD
VRP: 1.20
HV30: 22%
HV90: 24%
Momentum: 22 / 24 = 0.917 (stable)
Result: ✅ PASS
```

**Common Scenarios**:
- ✅ **0.85-1.00**: Normal range (vol stable or slightly declining)
- ⚠️ **0.70-0.85**: Moderate compression (borderline)
- ❌ **< 0.70**: Severe collapse (reject)

**Config**: `volatility_momentum_min_ratio: 0.85`

**Added**: ADR-0011 (2025-12-25) - Fills VRP 1.10-1.30 blind spot

---

### 6. **RetailEfficiencySpec** (Tastylive Mechanics)
**Purpose**: Ensure the underlying is practical for retail option traders.

**Checks**:
1. **Price Floor**: `price >= $25`
   - Below $25: Strike density too tight, gamma risk too high
2. **Slippage Guard**: `max(call_slippage, put_slippage) <= 5%`
   - Slippage = (Ask - Bid) / Mid
   - Prevents friction tax from wide markets

**Example**:
```
Symbol: /NG (Natural Gas)
Price: $3.76
Result: ❌ REJECT - Price too low (<$25)

Symbol: AAPL
Price: $150
Call Slippage: 2.1%
Put Slippage: 2.3%
Result: ✅ PASS
```

**Config**:
- `retail_min_price: 25.0`
- `retail_max_slippage: 0.05` (5%)

**Note**: Futures are NOT exempted (they should have clean spreads).

---

### 7. **IVPercentileSpec** (IV Rank Filter)
**Purpose**: Ensure IV is elevated vs its own 1-year range.

**Formula**:
```
IV Percentile >= 20

Where IV Percentile:
  0 = Lowest IV in past year
  50 = Middle of range
  100 = Highest IV in past year
```

**Rationale**: Even if VRP > 1.10 (IV > HV), we want IV to be elevated historically. IVP < 20 means IV is in bottom 20% of its range.

**Example**:
```
Symbol: MSFT
IV: 18%
IV Percentile: 15 (bottom 15% of 1-year range)
Result: ❌ REJECT - IV too low historically

Symbol: META
IV: 35%
IV Percentile: 78
Result: ✅ PASS
```

**Config**: `min_iv_percentile: 20.0`

**Futures Exemption**: Tastytrade doesn't provide IV Percentile for futures (`/ES`, `/CL`, etc.), so futures automatically pass this filter.

---

### 8. **LiquiditySpec** (Bid/Ask + Volume)
**Purpose**: Ensure you can enter/exit without excessive slippage.

**Primary Check** (Tastytrade liquidity rating):
```
liquidity_rating >= 4 (on 1-5 scale)

Where:
  5 = Excellent (tight markets, high volume)
  4 = Good
  3 = Fair
  2 = Poor
  1 = Very Poor
```

**Fallback Check** (if no Tastytrade rating):
1. Bid/Ask slippage <= 5%
2. ATM volume >= 500 contracts

**Safety Guard**: Even if rating >= 4, reject if slippage > 25% (data anomaly protection).

**Example**:
```
Symbol: SPY
Liquidity Rating: 5
Result: ✅ PASS

Symbol: OBSCURE_PENNY_STOCK
Liquidity Rating: 2
ATM Volume: 15
Result: ❌ REJECT
```

**Config**:
- `min_tt_liquidity_rating: 4`
- `min_atm_volume: 500` (fallback)
- `max_slippage_pct: 0.05` (fallback)

**Override**: `--allow-illiquid` bypasses this filter.

---

### 9. **CorrelationSpec** (Portfolio Diversification)
**Purpose**: Prevent adding correlated positions to portfolio.

**Formula**:
```
correlation(candidate_returns, portfolio_returns) <= 0.70
```

**Rationale**: If you already hold SPY, don't add QQQ (0.95 correlation). Limits concentration risk.

**Example**:
```
Portfolio: Holding SPY
Candidate: QQQ
Correlation: 0.95
Result: ❌ REJECT - Too correlated

Portfolio: Holding SPY
Candidate: GLD
Correlation: 0.15
Result: ✅ PASS - Diversifying
```

**Futures Proxy**: For futures without price history (e.g., `/ES`), uses ETF proxy (e.g., `SPY`) for correlation calculation. See `FAMILY_MAP` in config.

**Config**: `max_portfolio_correlation: 0.70`

**Skip**: Only applies when `--held-symbols` provided. Otherwise, correlation check is skipped.

---

## 🎯 Special Filter: Holding Filter (Scalable Gate)

**Applies**: Only for symbols you already hold (via `--held-symbols`).

**Logic**:
```python
if symbol in held_positions:
    if ScalableGateSpec.is_satisfied_by(metrics):
        # Show as "SCALE" - can add to position
        return True
    else:
        # HIDE - prevent over-trading
        return False
```

**ScalableGateSpec Triggers**:

Passes if **EITHER** condition is true:

1. **Absolute Markup Surge**: `vrp_tactical_markup >= 1.35`
   ```
   VRP Tactical Markup = (VRP Tactical - VRP Structural)

   Example:
     VRP Structural: 1.10 (baseline)
     VRP Tactical: 2.45 (surge!)
     Markup: 2.45 - 1.10 = 1.35 ✅ SCALABLE
   ```

2. **Relative Divergence**: `(vrp_tactical_markup + 1.0) / vrp_structural >= 1.10`
   ```
   Example:
     VRP Structural: 1.20
     VRP Tactical Markup: 0.12
     Divergence: (0.12 + 1.0) / 1.20 = 0.93 ❌ NOT SCALABLE
   ```

**Purpose**: Prevent adding to positions unless there's a **significant edge expansion**.

**Example**:
```
Position: Holding /ZN (10-Year Note)
VRP Structural: 1.79 (good edge)
VRP Tactical Markup: None (missing data)
Divergence: 0.558 (below 1.10)

Result: ❌ HIDDEN from screener (not scalable)
Why: Edge hasn't surged enough to justify adding
```

**Config**:
- `vrp_scalable_threshold: 1.35` (absolute markup)
- `scalable_divergence_threshold: 1.10` (relative divergence)

**To See Held Symbols**:
- Remove from `--held-symbols` temporarily
- Or wait for edge to surge above 1.35

---

## 📋 Filter Summary Table

| Filter | Checks | Threshold | Exemptions | Bypass Flag |
|--------|--------|-----------|------------|-------------|
| **DataIntegrity** | Data errors | N/A | Soft warnings | None |
| **VrpStructural** | IV / HV90 | > 1.10 | None | `--min-vrp 0` |
| **LowVolTrap** | HV252 floor | >= 5.0% | None | None |
| **VolatilityTrap** | HV Rank (if VRP>1.30) | >= 15 | Low VRP (<1.30) | None |
| **VolatilityMomentum** | HV30 / HV90 | >= 0.85 | Missing data | None |
| **RetailEfficiency** | Price + Slippage | >= $25, <= 5% | None | None |
| **IVPercentile** | IV Percentile | >= 20 | **Futures** | None |
| **Liquidity** | TT Rating or Volume | >= 4 or 500 | None | `--allow-illiquid` |
| **Correlation** | Portfolio rho | <= 0.70 | No holdings | None |
| **Scalable Gate** | Edge surge | >= 1.35 | New positions | Remove from `--held` |

---

## 🔍 Common Scenarios

### Scenario 1: "Why isn't AAPL showing up?"

**Diagnostic Steps**:
1. Check VRP: Is `VRP Structural > 1.10`?
2. Check IV Percentile: Is `IV Percentile >= 20`?
3. Check if held: Are you passing `--held-symbols AAPL`?
4. Check correlation: Do you hold SPY/QQQ (high correlation)?

**Common Causes**:
- VRP too low (IV not elevated enough)
- IV Percentile low (IV in bottom 20% of range)
- Already holding (needs scalable surge to show)
- High correlation with existing position

---

### Scenario 2: "Why aren't futures showing up?"

**Diagnostic Steps**:
1. Check VRP: Futures often have VRP < 1.10 during calm markets
2. Check price: /NG ($3.76) fails retail price floor ($25)
3. Check slippage: Wide spreads during holidays/after-hours
4. Check holdings: If you hold the future, needs scalable surge

**Common Causes**:
- **VRP too low** (most common - futures IV often matches HV closely)
- **Retail price floor** (e.g., /NG at $3.76 < $25)
- **Christmas data quality** (wide spreads, thin liquidity)
- **Already holding** (hidden unless scalable)

**Fix**: Run during market hours when futures have elevated IV.

---

### Scenario 3: "Symbol passes all filters but still rejected"

**Likely Cause**: **Holding Filter**

If you're passing `--held-symbols XYZ` and XYZ appears in the screener, it will ONLY show if:
- ScalableGateSpec passes (VRP Tactical Markup >= 1.35)
- Otherwise, it's **silently hidden** to prevent over-trading

**Solution**: Remove from `--held-symbols` temporarily to see it.

---

## 🛠️ Diagnostic Tool

Use the built-in diagnostic to troubleshoot filtering:

```bash
./variance diagnose AAPL
./variance diagnose /ES /CL /ZN
./variance diagnose --held TSLA
```

**Output**:
```
================================================================================
DIAGNOSING: AAPL
================================================================================

📊 Key Metrics:
   Price: $150.00
   VRP Structural: 1.22
   IV Percentile: 45
   HV30/HV90: 0.91

✅ DataIntegritySpec: True
✅ VrpStructuralSpec (>1.10): True
   VRP: 1.22 > 1.10
✅ VolatilityMomentumSpec (>0.85): True
   HV30/HV90: 0.91 > 0.85
❌ CorrelationSpec (<=0.70): False
   Correlation with SPY: 0.82

================================================================================
❌ RESULT: AAPL REJECTED by: Correlation
================================================================================
```

See `docs/user-guide/diagnostic-tool.md` for full documentation.

---

## 📚 References

- **ADR-0010**: VRP Threshold Calibration (HV90 methodology)
- **ADR-0011**: Volatility Spec Separation (Positional vs Momentum)
- **ADR-0008**: Multi-Provider Architecture (Tastytrade integration)
- **Config**: `config/trading_rules.json` (threshold values)
- **Code**: `src/variance/models/market_specs.py` (filter implementations)

---

## 🔧 Tuning Recommendations

### Conservative (Fewer Candidates, Higher Quality)
```json
{
  "vrp_structural_threshold": 1.20,
  "min_iv_percentile": 30.0,
  "volatility_momentum_min_ratio": 0.90,
  "max_portfolio_correlation": 0.60
}
```

### Aggressive (More Candidates, Lower Bar)
```json
{
  "vrp_structural_threshold": 1.00,
  "min_iv_percentile": 10.0,
  "volatility_momentum_min_ratio": 0.80,
  "max_portfolio_correlation": 0.80
}
```

### Current (Balanced - Default)
```json
{
  "vrp_structural_threshold": 1.10,
  "min_iv_percentile": 20.0,
  "volatility_momentum_min_ratio": 0.85,
  "max_portfolio_correlation": 0.70
}
```

---

**Version History**:
- **2.0** (2025-12-25): HV90/HV30 methodology, VolatilityMomentumSpec added
- **1.5** (2025-12-25): Futures IV Percentile exemption, market hours cache
- **1.0** (2025-12-20): Initial Tastytrade integration
