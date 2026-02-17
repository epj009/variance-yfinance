# Variance Audit Action Items
**Date:** 2025-12-29
**Source:** PROJECT_STATUS_AUDIT_2025-12-29.md

---

## CRITICAL (Fix Immediately)

### 1. Update System Prompt - INCORRECT Futures IV Percentile Information

**File:** `variance-system-prompt.md`
**Lines:** 65-71

**Current (WRONG):**
```markdown
7. **IV Percentile** - IVP ≥ 20 (IV above 20th percentile of 1-year range) *Futures exempt*

**Futures Exemptions:**
- IV Percentile filter: Auto-pass (Tastytrade doesn't provide IVP for futures)
- Use ETF proxy IV when futures symbol starts with `/`
```

**Should be:**
```markdown
7. **IV Percentile** - IVP ≥ 20 (IV above 20th percentile of 1-year range)

**Note:** Tastytrade provides IV Percentile for both equities and futures. All symbols are subject to this filter.
```

**Why Critical:** AI agents using this prompt will give INCORRECT advice to users about futures filtering.

**Verified:** Code DOES require futures to pass IV Percentile check (commit ba5e298 fixed this bug).

---

## HIGH Priority (Fix This Week)

### 2. Resolve VRP Structural Threshold Inconsistency

**Issue:** Config file shows 1.00, but ADR-0010 and docs reference 1.10

**Evidence:**
- `config/trading_rules.json` line 2: `"vrp_structural_threshold": 1.00`
- `docs/adr/0010-vrp-threshold-calibration-hv90.md` line 63: "New Threshold = 1.10"
- `docs/user-guide/config-guide.md` line 29: "1.10 (balanced - current default)"

**Action Required:**
1. Verify with user which is correct (1.00 or 1.10)
2. If 1.10 is correct: Update `config/trading_rules.json` line 2
3. If 1.00 is correct: Update ADR-0010 and config-guide.md with explanation

**Impact:** Affects candidate selection - 1.00 is more permissive than 1.10

---

### 3. Fix RetailEfficiencySpec Documentation

**File:** `docs/user-guide/filtering-rules.md`
**Line:** 225

**Current (WRONG):**
```markdown
**Note**: Futures are NOT exempted (they should have clean spreads).
```

**Actual Code Behavior:**
```python
# src/variance/models/market_specs.py:403
if symbol.startswith("/"):
    return True  # Futures exemption
```

**Should be:**
```markdown
**Note**: Futures symbols (starting with `/`) are EXEMPTED from price floor and slippage checks.
```

**Why Important:** Docs claim futures are checked, but code exempts them. Users need accurate information.

---

## MEDIUM Priority (Fix This Sprint)

### 4. Update Legacy Fallback Defaults

**File:** `src/variance/screening/steps/filter.py`
**Line:** 41

**Current:**
```python
rules.get("vrp_structural_threshold", 0.85)  # HV252-era default
```

**Should be:**
```python
rules.get("vrp_structural_threshold", 1.10)  # HV90-era default
```

**Why:** Fallback default is from old HV252 calibration. Should match current HV90 calibration (1.10).

**Impact:** Low (config always overrides), but improves consistency.

**Other Defaults to Update:**
- Line 47: `vrp_rich_threshold` fallback: 1.0 → 1.30
- Line 48: `vrp_tactical_threshold` fallback: 1.15 (already correct)

---

### 5. Add Missing Unit Tests

**Tests to Add:**

1. **DataIntegritySpec Explicit Test**
   ```python
   def test_data_integrity_spec_soft_warnings():
       spec = DataIntegritySpec()
       assert spec.is_satisfied_by({"warning": "iv_scale_corrected"}) is True
       assert spec.is_satisfied_by({"warning": "critical_error"}) is False
   ```

2. **Filter Composition Order Test**
   ```python
   def test_filter_order_data_integrity_first():
       # Verify DataIntegritySpec runs before expensive filters
       pass
   ```

3. **CLI Override Integration Test**
   ```python
   def test_min_vrp_zero_bypasses_filter():
       # Test that --min-vrp 0.0 bypasses VrpStructuralSpec
       pass
   ```

**Priority:** Medium (good to have, not blocking)

---

## LOW Priority (Backlog)

### 6. Deprecate Redundant Config Parameter

**Issue:** `tastytrade_iv_percentile_floor` duplicates `min_iv_percentile`

**Evidence:**
- `config/trading_rules.json` line 9: `"tastytrade_iv_percentile_floor": 20.0`
- `config/trading_rules.json` line 8: `"min_iv_percentile": 30.0`

**Action:**
1. Add deprecation warning in code
2. Update docs to note parameter is deprecated
3. Remove in next major version (v2.0)

**Status:** Already documented in `docs/maintenance/unused-config-settings.md`

---

## VERIFIED AS CORRECT (No Action Needed)

✅ **All filters properly configurable** - No hardcoded thresholds found

✅ **Recent IV Percentile bug fix (commit ba5e298)** - Correctly removes futures exemption

✅ **Volatility spec separation (ADR-0011)** - Correctly implemented, blind spot fixed

✅ **Configuration documentation** - 100% parameter coverage (56/56)

✅ **Test coverage** - All critical filters have unit tests

✅ **No execution code** - Execution isolation mandate verified

✅ **Registry pattern** - Properly implemented, no factory.py modifications

---

## Summary Statistics

- **Total Issues Found:** 6
- **Critical:** 1 (system prompt)
- **High:** 2 (VRP threshold, RetailEfficiencySpec docs)
- **Medium:** 2 (legacy fallbacks, missing tests)
- **Low:** 1 (redundant config param)

**Overall Project Health:** ✅ HEALTHY

**Confidence in Findings:** 95%

---

## Quick Wins (< 5 minutes each)

1. Update `variance-system-prompt.md` lines 65-71 (remove futures exemption language)
2. Update `docs/user-guide/filtering-rules.md` line 225 (clarify futures ARE exempted from RetailEfficiencySpec)
3. Update `src/variance/screening/steps/filter.py` line 41 default from 0.85 → 1.10

**Estimated Total Time for All Quick Wins:** 15 minutes

---

**Next Steps:**
1. Review this action list with user
2. Prioritize fixes (recommend tackling CRITICAL + HIGH this week)
3. Create GitHub issues for MEDIUM/LOW items
4. Schedule next audit for Q1 2026
