# VRP Threshold Update Summary - Quick Reference

## What Changed

```diff
# config/trading_rules.json

- "vrp_structural_threshold": 0.85        (OLD - calibrated for HV252)
+ "vrp_structural_threshold": 1.10        (NEW - calibrated for HV90)

- "vrp_structural_rich_threshold": 0.95   (OLD)
+ "vrp_structural_rich_threshold": 1.30   (NEW)

- "vrp_tactical_threshold": 0.90          (OLD - calibrated for HV20)
+ "vrp_tactical_threshold": 1.15          (NEW - calibrated for HV30)
```

**Increase:** ~30% across the board

---

## Why This Was Necessary

### Diagnostic Results (13 Symbol Test)

| Threshold | HV252 Pass Rate | HV90 Pass Rate (Old Threshold) | HV90 Pass Rate (New Threshold) |
|-----------|-----------------|--------------------------------|--------------------------------|
| **0.85** (old) | 1/13 (7.7%) | **11/13 (84.6%)** ⚠️ | N/A |
| **1.10** (new) | N/A | N/A | **5/13 (38.5%)** ✅ |

**Without adjustment:** Screener became 11x more permissive (too loose).
**With adjustment:** Screener maintains reasonable selectivity.

---

## Expected Behavior

### Before (HV252 @ 0.85)
```bash
./variance --tui --debug

SCREENER OUTPUT:
  Candidates: 2-5 symbols (very strict)
  Rejections:
    - Low VRP: 245 symbols
    - Illiquid: 45 symbols
```

### After (HV90 @ 1.10)
```bash
./variance --tui --debug

SCREENER OUTPUT:
  Candidates: 10-30 symbols (moderate selectivity)
  Rejections:
    - Low VRP: 180 symbols (fewer, but still selective)
    - Illiquid: 45 symbols (unchanged)
```

**Interpretation:**
- More candidates than before (tactical opportunities)
- Still selective (60% rejection rate)
- Better regime adaptation

---

## Validation Steps

### Step 1: Run the Screener

```bash
./variance --tui --debug
```

### Step 2: Check Candidate Counts

**Expected Range:** 10-30 candidates

**Too Many (>50)?**
- Thresholds too loose
- Raise to 1.20 / 1.40 / 1.25

**Too Few (<5)?**
- Thresholds too tight (or market genuinely cheap)
- Lower to 1.00 / 1.20 / 1.10

### Step 3: Review Sample Candidates

**Good Signs:**
- VRP Structural: 1.10 - 1.40 range
- Mix of sectors (not all one industry)
- Includes known names (AAPL, SPY, etc.)

**Bad Signs:**
- VRP > 2.0 (overly permissive)
- All low-quality stocks
- Obvious garbage (penny stocks, illiquid)

### Step 4: Compare VRP Values

**Before (Example):**
```
AAPL: VRP = 0.577 (HV252) → Rejected
SPY:  VRP = 0.681 (HV252) → Rejected
```

**After (Example):**
```
AAPL: VRP = 1.054 (HV90) → Passes (< 1.10? No, >= 1.10? No, close)
SPY:  VRP = 1.061 (HV90) → Passes (barely)
```

---

## If Results Look Wrong

### Scenario A: WAY Too Many Candidates (>80% pass rate)

**Diagnosis:** Market is in extreme low-vol regime, or thresholds still too low.

**Fix:**
```json
{
  "vrp_structural_threshold": 1.25,
  "vrp_structural_rich_threshold": 1.50,
  "vrp_tactical_threshold": 1.30
}
```

### Scenario B: Zero Candidates

**Diagnosis:** Market is cheap (IV < HV), or thresholds too aggressive.

**Check:**
```bash
# Run diagnostic to see actual VRP values
./venv/bin/python3 scripts/compare_hv_sources.py
```

If average VRP < 1.0, market is genuinely cheap (not a threshold issue).

**If needed, lower thresholds:**
```json
{
  "vrp_structural_threshold": 1.00,
  "vrp_structural_rich_threshold": 1.20,
  "vrp_tactical_threshold": 1.05
}
```

### Scenario C: Results Look Good (10-30 candidates)

**Action:** None needed, thresholds are calibrated correctly!

---

## Rollback Instructions

If you want to go back to HV252-based approach:

### 1. Revert Thresholds
```json
{
  "vrp_structural_threshold": 0.85,
  "vrp_structural_rich_threshold": 0.95,
  "vrp_tactical_threshold": 0.90
}
```

### 2. Revert VRP Calculation Priority

Edit `src/variance/get_market_data.py:841-858`:

```python
# Change priority: HV252 first, HV90 fallback
if hv252 is not None and hv252 > 0:
    merged_data["vrp_structural"] = iv / max(hv252, hv_floor)
elif hv90 is not None and hv90 > 0:
    merged_data["vrp_structural"] = iv / max(hv90, hv_floor)

# Tactical: HV20 first, HV30 fallback
if hv20 is not None:
    merged_data["vrp_tactical"] = iv / max(hv20, hv_floor)
elif hv30 is not None:
    merged_data["vrp_tactical"] = iv / max(hv30, hv_floor)
```

### 3. Test
```bash
./variance --tui --debug
```

Should see 2-5 candidates (very strict) again.

---

## Monitoring Over Time

**Re-run diagnostic monthly:**
```bash
./venv/bin/python3 scripts/compare_hv_sources.py
```

**Watch for ratio changes:**
- Dec 2025: 1.30x (low-vol regime)
- If ratio goes to 1.50x → Raise thresholds
- If ratio goes to 1.10x → Lower thresholds

**Threshold drift indicator:**
- If candidate count changes dramatically week-to-week
- If all symbols suddenly pass/fail
- Re-calibrate using diagnostic script

---

## Quick Reference Card

| Setting | Old (HV252) | New (HV90) | Change |
|---------|-------------|------------|--------|
| Structural Threshold | 0.85 | **1.10** | +29% |
| Rich Threshold | 0.95 | **1.30** | +37% |
| Tactical Threshold | 0.90 | **1.15** | +28% |
| Expected Pass Rate | 7-10% | **30-40%** | 4x more |
| VRP Multiplier | 1.00x | **1.30x** | +30% |

---

## Summary

✅ **Thresholds Updated:** 0.85 → 1.10 (structural), 0.95 → 1.30 (rich), 0.90 → 1.15 (tactical)
✅ **Calibration Basis:** Empirical testing on 13 symbols (1.30x ratio)
✅ **Expected Impact:** 10-30 candidates (vs 2-5 before)
✅ **Philosophy Shift:** Strategic extremes → Tactical opportunities

**Next Step:** Run `./variance --tui --debug` and verify candidate counts look reasonable!
