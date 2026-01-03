# ADR-0014: Volatility Trend Ratio Rename

**Status:** Accepted
**Date:** 2026-01-02
**Deciders:** Product Manager, Architect
**Technical Story:** Semantic Inversion Fix

## Context

The metric previously called "Compression Ratio" (HV30/HV90) suffered from a semantic inversion problem that caused confusion in signal interpretation and trading decisions.

### The Problem

**Original Formula:** `Compression Ratio = HV30 / HV90`

**Semantic Conflict:**
- **Name implies:** Lower ratio = "compressed" (coiled spring ready to expand)
- **Actual meaning:** Lower ratio = HV30 < HV90 = volatility is CONTRACTING (not compressed)
- **Signal confusion:** Traders expected "compression" to mean "ready to explode," but the metric indicated the opposite

### Quant Research Findings

Analysis of volatility regimes revealed:

1. **HV30/HV90 < 0.75** ("Compressed")
   - **Reality:** Recent volatility (HV30) is 75% or less of 90-day volatility
   - **True State:** Volatility is CONTRACTING/DECLINING
   - **Market Risk:** Avoid selling premium (low IV environment, mean reversion risk upward)
   - **Signal:** COILED (waiting for expansion)

2. **HV30/HV90 > 1.15** ("Expanded")
   - **Reality:** Recent volatility is 115%+ of 90-day volatility
   - **True State:** Volatility is EXPANDING/INCREASING
   - **Market Opportunity:** Sell premium (high IV environment, likely to contract)
   - **Signal:** EXPANDING (good for short vol)

3. **HV30/HV90 ≈ 1.0** ("Normal")
   - **Reality:** Recent volatility matches 90-day average
   - **True State:** Stable volatility trend
   - **Signal:** FAIR (no regime signal)

### Why "Compression Ratio" Was Misleading

The term "compression" suggested a **coiled spring** metaphor (compressed → about to expand), but the math showed the opposite:
- **Low ratio (0.60):** Volatility is DECLINING (not compressed)
- **High ratio (1.30):** Volatility is EXPANDING (not already expanded)

This inversion led to:
- Incorrect triage actions
- Confusing signals in TUI
- Documentation that required constant mental translation

## Decision

Rename **"Compression Ratio"** to **"Volatility Trend Ratio" (VTR)**.

### Rationale

**"Volatility Trend Ratio"** is semantically correct:
- **VTR < 0.75:** Recent volatility is LOWER than 90-day average (downtrend)
- **VTR > 1.15:** Recent volatility is HIGHER than 90-day average (uptrend)
- **VTR ≈ 1.0:** Recent volatility MATCHES 90-day average (stable)

The name directly describes what the metric measures: **the trend direction of volatility**.

## Implementation

### 1. Formula (Unchanged)

```python
VTR = HV30 / HV90
```

All threshold values remain unchanged:
- `vtr_coiled_threshold = 0.75` (was `compression_coiled_threshold`)
- `vol_trap_vtr_threshold = 0.70` (was `vol_trap_compression_threshold`)

### 2. Field Key Changes

**Candidate Dictionary:**
- **New:** `"Volatility Trend Ratio"` (primary)
- **Deprecated:** `"Compression Ratio"` (backward compatibility alias)

**Display Dictionary:**
- **New:** `"VTR"` (TUI column header)
- **Deprecated:** `"Compression"` (removed)

### 3. Config Key Migration

**New Config Keys:**
- `vtr_coiled_threshold` (replaces `compression_coiled_threshold`)
- `vol_trap_vtr_threshold` (replaces `vol_trap_compression_threshold`)

**Backward Compatibility:**
- Old keys still work with `DeprecationWarning`
- Migration helper: `config_migration.get_config_value()`
- Automatic migration: `config_migration.migrate_config_keys()`

### 4. Signal Function Updates

**Updated Parameter Names:**
- `determine_signal_type(..., vol_trend_ratio=...)` (was `compression_ratio`)
- `determine_regime_type(..., vol_trend_ratio=...)` (was `compression_ratio`)

**Updated Docstrings:**
- Changed "compression ratio" references to "Volatility Trend Ratio"
- Updated formulas and descriptions

### 5. Files Modified

**Core Logic:**
- `src/variance/config_migration.py` (new)
- `src/variance/screening/enrichment/vrp.py`
- `src/variance/signals/classifier.py`
- `src/variance/signals/regime.py`
- `src/variance/screening/steps/report.py`
- `src/variance/tui_renderer.py`

**Config:**
- `config/trading_rules.json`
- `config/trading_rules.reorganized.json`
- `config/trading_rules.v2.json`

**Tests:**
- `tests/test_vote_logic.py`
- `tests/test_signal_synthesis.py`
- `tests/test_vol_screener.py`

**Documentation:**
- `docs/adr/0014-volatility-trend-ratio-rename.md` (this file)

### 6. Backward Compatibility Strategy

**Phase 1: Dual-Key Period (v1.9.x - Current)**
- Both old and new keys work
- Deprecation warnings on old key usage
- TUI displays "VTR" column header
- Reports include both field keys

**Phase 2: Deprecation (v2.0.0 - Future)**
- Remove old config keys
- Remove `"Compression Ratio"` field alias
- Update all documentation to remove old terminology

**Migration Guide:**

**Old Config:**
```json
{
  "compression_coiled_threshold": 0.75,
  "vol_trap_compression_threshold": 0.70
}
```

**New Config:**
```json
{
  "vtr_coiled_threshold": 0.75,
  "vol_trap_vtr_threshold": 0.70
}
```

**Old Code:**
```python
candidate["Compression Ratio"]
```

**New Code:**
```python
candidate["Volatility Trend Ratio"]
```

## Consequences

### Positive

1. **Semantic Clarity:** Name matches the metric's actual behavior
2. **Reduced Confusion:** No more mental translation required
3. **Better Signals:** Traders can quickly interpret VTR values
4. **Documentation Alignment:** Docs now use consistent, correct terminology
5. **No Breaking Changes:** Old configs continue to work with warnings

### Negative

1. **Migration Effort:** Users must update config files (but not required immediately)
2. **Documentation Updates:** All user guides need terminology updates
3. **Learning Curve:** Users must learn new terminology (but it's more intuitive)

### Neutral

1. **No Formula Changes:** All math and thresholds remain unchanged
2. **No Performance Impact:** Pure rename operation

## Validation

### Test Coverage

All tests pass with new terminology:
- `tests/test_vote_logic.py` (3 tests)
- `tests/test_signal_synthesis.py` (8 tests)
- `tests/test_vol_screener.py` (1 test)

### Backward Compatibility Verified

- Old config keys work with deprecation warnings
- Old field keys work via alias
- No breaking changes to existing scripts

## Related Decisions

- **ADR-0013:** Compression Ratio Decision Framework (now refers to VTR)
- **RFC-021:** Intent-Based Earnings Detection (uses VTR terminology)

## References

- **Original Implementation:** `src/variance/screening/enrichment/vrp.py` (line 23-38)
- **Signal Logic:** `src/variance/signals/classifier.py` (line 68-87)
- **Regime Detection:** `src/variance/signals/regime.py` (line 6-38)
- **Vote Logic:** `src/variance/screening/steps/report.py` (line 19-53)
- **TUI Display:** `src/variance/tui_renderer.py` (line 418, 481-500)

---

**Implementation Date:** 2026-01-02
**Author:** Developer Agent (ac5cb03)
**Review Status:** Approved
