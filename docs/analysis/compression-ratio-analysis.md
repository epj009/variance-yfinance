# Compression Ratio Analysis: Continuous vs Discrete

**Date:** December 31, 2025
**Context:** Quant agent recommended using continuous Compression Ratio instead of 3-bucket Regime labels

---

## TL;DR

**Finding:** You're ALREADY using the continuous Compression Ratio (under the name "volatility_momentum"), but you're ALSO creating redundant binary flags that lose information.

**Recommendation:**
1. Display the actual Compression Ratio value in TUI (more useful than "BOUND" label)
2. Consider deprecating `is_coiled` and `is_expanding` flags
3. Use threshold checks directly on the continuous ratio when needed

---

## Current State: Duplication and Information Loss

### The Same Metric, Three Different Names

| Name | Formula | Usage | Thresholds |
|------|---------|-------|------------|
| **Compression Ratio** | HV30 / HV90 | Stored in candidate dict | None (raw value) |
| **volatility_momentum** | HV30 / HV90 | Variance Score (10% weight) | 0.85 - 1.20 |
| **is_coiled flag** | HV30 / HV90 | Binary flag → Signal = "BOUND" | < 0.75 |
| **is_expanding flag** | HV30 / HV90 | Binary flag → (unused) | > 1.25 |

**They're all the SAME underlying metric!**

---

## The Information Loss Problem

### Continuous → Discrete Bucketing

**Scenario:** Three stocks with different compression states:

| Stock | Compression Ratio | Current Label | Information Lost |
|-------|------------------|---------------|------------------|
| AAPL | 0.72 | COILED (< 0.75) | Barely coiled, near threshold |
| TSLA | 0.50 | COILED (< 0.75) | Severely compressed, explosive potential |
| SPY | 0.95 | NORMAL (0.75-1.25) | Slight compression, stable |

**Problem:** AAPL (0.72) and TSLA (0.50) both labeled "COILED" but have very different risk profiles!

### What You're Throwing Away

**Continuous Ratio Value:**
- 0.50 = HV is 50% of long-term average (severe spring)
- 0.72 = HV is 72% of average (mild compression)
- 0.95 = HV is 95% of average (nearly normal)
- 1.30 = HV is 130% of average (expanding volatility)

**Binary Flag Value:**
- is_coiled = True (all compression treated the same)
- is_coiled = False (everything else)

**You lose the DEGREE of compression.**

---

## Where Compression Ratio is Currently Used

### 1. Calculated and Stored (✅ Good)

**File:** `src/variance/screening/enrichment/vrp.py:24-30`

```python
candidate["Compression Ratio"] = 1.0
try:
    if hv30 is not None and hv90 is not None:
        hv90_f = float(hv90)
        if hv90_f > 0:
            candidate["Compression Ratio"] = float(hv30) / hv90_f
```

**Status:** Calculated correctly, stored in dict

---

### 2. Used in Variance Score (✅ Good - Using Continuous Value)

**File:** `src/variance/vol_screener.py:371-386`

```python
def _score_volatility_momentum(metrics: dict[str, Any], rules: dict[str, Any]) -> float:
    hv30 = metrics.get("hv30")
    hv90 = metrics.get("hv90")
    # ...
    ratio = float(hv30) / hv90_f  # Continuous value!

    floor = 0.85  # Below this = bad (contracting vol)
    ceiling = 1.20  # Above this = neutral (expanding vol)
    return _normalize_score(ratio, floor, ceiling)
```

**Weighting:** 10% of Variance Score

**Score Behavior:**
- ratio = 0.60 → Score = 0 (severe contraction, avoid)
- ratio = 0.85 → Score = 50 (floor threshold)
- ratio = 1.00 → Score = ~70 (neutral momentum)
- ratio = 1.20 → Score = 100 (ceiling, good momentum)

**This is GREAT!** You're using the continuous value here.

---

### 3. Converted to Binary Flags (⚠️ Information Loss)

**File:** `src/variance/vol_screener.py:213-238`

```python
is_coiled_long = compression_ratio < 0.75  # Binary threshold
is_expanding = compression_ratio > 1.25    # Binary threshold
```

**Then used for:**
- `is_coiled` → Signal = "BOUND" (TUI display only)
- `is_expanding` → Nothing (orphaned, as we discovered)

**Problem:** This discretizes a continuous metric into buckets.

---

### 4. Used in VolatilityMomentumSpec Filter (❌ ORPHANED)

**File:** `src/variance/models/market_specs.py:329-375`

```python
class VolatilityMomentumSpec(Specification):
    """Rejects symbols where HV30/HV90 < 0.85"""

    def is_satisfied_by(self, metrics: dict[str, Any]) -> bool:
        momentum = float(hv30) / float(hv90)
        return momentum >= self.min_momentum_ratio  # 0.85 default
```

**Status:** Defined but NEVER USED in filter pipeline (auditor found this)

**Evidence:** `grep` shows it's imported but not instantiated in `screening/steps/filter.py`

---

## The Quant's Recommendation: Use Continuous Values

### What "Use Compression Ratio Directly" Means

Instead of:
```python
# Current: Lose information via bucketing
if is_coiled:
    signal = "BOUND"
    # User sees "BOUND" but doesn't know if it's 0.50 or 0.74
```

Do this:
```python
# Better: Show the actual value
compression = candidate["Compression Ratio"]
if compression < 0.75:
    signal = f"COILED ({compression:.2f})"  # "COILED (0.52)"
    # User sees the severity
```

Or even better:
```python
# Best: Make decisions based on continuous value
if compression < 0.60:
    recommendation = "HIGH CONVICTION - Severe compression"
elif compression < 0.75:
    recommendation = "MODERATE - Mild compression"
elif compression > 1.25:
    recommendation = "CAUTION - Expanding volatility"
```

---

## Concrete Improvements

### Option 1: Display Compression Ratio in TUI

**Current TUI columns:**
```
Symbol | VRP_T | VRP_S | IVP | Rho | Yield | Earn | Signal | Vote
AAPL   | 4.20  | 2.15  | 85  | 0.3 | 8.5%  | 12   | BOUND  | BUY
```

**Proposed (add Compression column):**
```
Symbol | VRP_T | VRP_S | Comp | IVP | Rho | Yield | Earn | Signal | Vote
AAPL   | 4.20  | 2.15  | 0.52 | 85  | 0.3 | 8.5%  | 12   | BOUND  | BUY
TSLA   | 3.80  | 2.00  | 0.74 | 80  | 0.4 | 7.2%  | 5    | BOUND  | LEAN
SPY    | 2.10  | 1.40  | 0.95 | 70  | 0.5 | 6.0%  | N/A  | RICH   | LEAN
```

**Benefit:** User sees AAPL (0.52) is MORE compressed than TSLA (0.74), both labeled "BOUND"

---

### Option 2: Use Compression in Vote Logic

**Current Vote logic:**
```python
# vote.py:103-118
if score >= 70 and rho <= 0.50:
    vote = "BUY"
elif score >= 60 and rho <= 0.65:
    vote = "LEAN"
```

**Proposed (add compression boost):**
```python
# Enhanced: Boost BUY confidence for severe compression
if score >= 70 and rho <= 0.50:
    compression = candidate.get("Compression Ratio", 1.0)
    if compression < 0.60:  # Severe coiling
        vote = "STRONG BUY"  # Higher conviction
    else:
        vote = "BUY"
elif score >= 60 and rho <= 0.65:
    vote = "LEAN"
```

**Quantitative Justification:**
- Compression < 0.60 means HV is 40%+ below average
- Historical mean reversion probability is higher
- Warrants higher allocation confidence

---

### Option 3: Deprecate Binary Flags

**What to Remove:**
1. `is_coiled` flag → Use `compression_ratio < 0.75` directly
2. `is_expanding` flag → Already orphaned, delete it
3. `Signal = "BOUND"` label → Replace with continuous compression display

**Benefits:**
- Fewer intermediate variables
- Less cognitive load
- More information to users
- Simpler code

**Migration:**
```python
# Before (binary flag)
if candidate["is_coiled"]:
    signal = "BOUND"

# After (continuous threshold check)
compression = candidate["Compression Ratio"]
if compression < 0.75:
    signal = f"COILED-{compression:.2f}"
```

---

### Option 4: Complete VolatilityMomentumSpec Integration

**Current Status:** Spec is defined but NOT in filter pipeline

**Two choices:**

**A) Add it to pipeline:**
```python
# screening/steps/filter.py:74
main_spec &= VolatilityMomentumSpec(min_momentum_ratio=0.85)
```

**Effect:** Hard gate - reject any stock with compression < 0.85

**B) Delete it:**
- It's already redundant with variance score's `volatility_momentum` component
- No need for both a filter AND a score component

**Quant's likely recommendation:** Delete it (redundant)

---

## Comparison: Discrete vs Continuous

| Aspect | Binary Flags (Current) | Continuous Ratio (Recommended) |
|--------|----------------------|-------------------------------|
| **Information** | 3 buckets (COILED/NORMAL/EXPANDING) | Infinite granularity (0.0 - 2.0+) |
| **User Insight** | "It's coiled" | "It's 52% of normal vol (severe)" |
| **Decision Making** | Coarse thresholds | Nuanced thresholds |
| **False Precision** | 0.74 and 0.50 both "COILED" | 0.74 ≠ 0.50 (different risk) |
| **Code Complexity** | Extra flag variables | Direct ratio checks |
| **Maintenance** | Must sync flag logic with thresholds | One source of truth |

---

## Recommended Actions

### Priority 1: Display Compression Ratio in TUI (High Value, Low Effort)

**Change:** Add "Comp" column to TUI table

**Files to modify:**
- `src/variance/tui_renderer.py` (add column)
- `src/variance/screening/steps/report.py` (ensure ratio is in display dict)

**Impact:** Users immediately see compression severity, not just binary label

---

### Priority 2: Delete is_expanding Flag (Already Orphaned)

**Change:** Remove `is_expanding` from flag creation

**Files to modify:**
- `src/variance/vol_screener.py:236-239` (remove flag)
- `config/trading_rules.json` (remove `compression_expanding_threshold` config)

**Impact:** Clean up orphaned code

---

### Priority 3: Consider Continuous Thresholds in Decision Logic

**Research Question:** Should Vote or Signal use compression degree?

**Example:**
```python
# Current
if is_coiled:  # Binary
    signal = "BOUND"

# Proposed
compression = candidate["Compression Ratio"]
if compression < 0.60:
    signal = "COILED-SEVERE"  # High conviction
elif compression < 0.75:
    signal = "COILED-MILD"   # Moderate conviction
else:
    signal = "NEUTRAL"
```

**Needs:** Backtest validation before implementing

---

### Priority 4: Delete or Activate VolatilityMomentumSpec

**Two options:**
- **Delete:** It's redundant with variance score's momentum component
- **Activate:** Add to filter pipeline at line 74 of `filter.py`

**Recommendation:** Delete (same information, different threshold - confusing)

---

## Example: Real-World Scenario

**Portfolio Decision:**

| Stock | Compression Ratio | Current Label | Recommended Action |
|-------|------------------|---------------|-------------------|
| **NVDA** | 0.48 | COILED | STRONG BUY - Extreme compression (52% below average HV) |
| **AMD** | 0.70 | COILED | BUY - Moderate compression |
| **INTC** | 0.76 | NORMAL | LEAN - Just above coiled threshold |
| **QCOM** | 1.15 | NORMAL | WATCH - Slightly expanding |
| **AVGO** | 1.35 | EXPANDING | AVOID - Volatility accelerating |

**With Binary Flags:** NVDA and AMD both "COILED" (no differentiation)

**With Continuous Ratio:** NVDA (0.48) has 31% MORE compression than AMD (0.70) → Higher conviction

---

## Summary: What the Quant Agent Meant

> "Use the continuous Compression Ratio directly - it's more powerful than the 3-bucket Regime label."

**Translation:**
1. You're already storing `candidate["Compression Ratio"]` (good!)
2. You're already using it in variance score (good!)
3. But you're ALSO creating binary flags that lose information (bad!)
4. **Solution:** Display the actual ratio, use it in decisions, deprecate the flags

**The ratio itself IS the regime indicator** - you don't need separate labels.

**Math:**
- 0.40-0.60: Severe coiling (explosive potential)
- 0.60-0.75: Moderate coiling
- 0.75-1.15: Normal volatility
- 1.15-1.30: Expanding (caution)
- 1.30+: Accelerating (avoid short vol)

Use these thresholds directly on the continuous value!
