# ADR 0011: Volatility Specification Separation (Positional vs Momentum)

**Status:** ✅ Accepted
**Date:** 2025-12-25
**Decision Makers:** Product (User), Engineering (Claude)
**Tags:** #specifications #volatility #whipsaw-protection #refactoring

---

## Context

The current `VolatilityTrapSpec` violates the Single Responsibility Principle by performing two distinct checks:

1. **Positional Check:** "Is HV at an extreme low of its 1-year range?" (HV Rank < 15)
2. **Compression Check:** "Is volatility currently collapsing?" (HV30/HV90 < 0.70)

### The Problem

**From `market_specs.py:292-324` (before refactoring):**

```python
class VolatilityTrapSpec(Specification[dict[str, Any]]):
    """
    Hard gate against Volatility Traps.
    Rejects symbols where realized volatility is either:
    1. Positional: Extreme low of its 1-year range (HV Rank < 15)
    2. Relative: Extremely compressed vs its own medium-term trend (HV30 / HV90 < 0.70)
    """

    def is_satisfied_by(self, metrics: dict[str, Any]) -> bool:
        # Only apply trap logic if the symbol looks "Rich"
        if vrp_s is not None and float(vrp_s) > self.vrp_rich_threshold:  # 1.30
            # Trigger 1: Positional Rank
            if hv_rank is not None and float(hv_rank) < self.rank_threshold:
                return False

            # Trigger 2: Relative Compression
            if hv30 and hv90 and float(hv90) > 0:
                if (float(hv30) / float(hv90)) < self.compression_threshold:
                    return False

        return True
```

**Issues with this design:**

1. **Blind Spot:** Compression check is ONLY applied when VRP > 1.30
   - Symbols with VRP 1.10-1.30 can pass even if volatility is collapsing
   - Example: VRP=1.15, HV30/HV90=0.60 → ✅ PASSES (should reject)

2. **Conflated Logic:** Two unrelated checks bundled in one spec
   - HV Rank = long-term positional context (1 year)
   - HV30/HV90 = short-term momentum (quarterly)
   - Makes testing and reasoning more complex

3. **Not Composable:** Can't apply compression check independently
   - Specification pattern designed for `&`, `|`, `~` composition
   - Current design locks compression behind VRP gate

### Example of the Blind Spot

```
Symbol: XYZ
VRP Structural: 1.15 (passes 1.10 threshold)
HV Rank: 45 (mid-range, passes)
HV30: 12%
HV90: 20%
Compression Ratio: 12/20 = 0.60 (40% collapse!)

Current Behavior:
✅ PASSES - VRP (1.15) < vrp_rich_threshold (1.30)
→ Compression check NEVER RUNS
→ Whipsaw risk: Entered a "rich IV" trade but HV keeps falling

Desired Behavior:
❌ REJECTS - Universal compression check catches the collapse
```

---

## Decision

**Split `VolatilityTrapSpec` into two standalone specifications:**

1. **VolatilityTrapSpec** (Refactored) - Positional check only
2. **VolatilityMomentumSpec** (New) - Universal compression check

### VolatilityTrapSpec (Positional Only)

**Single Responsibility:** "Is realized volatility at an extreme low of its 1-year range?"

```python
class VolatilityTrapSpec(Specification[dict[str, Any]]):
    """
    Hard gate against Volatility Traps (Positional).

    Rejects symbols where HV Rank < 15 (extreme low of 1-year range).
    Only applies when VRP > rich_threshold (1.30) to focus on "rich IV" setups.

    Rationale: If IV is rich (>1.30) but HV is at yearly lows (<15 percentile),
    you're likely catching a falling knife (vol compression mid-trade risk).

    Args:
        rank_threshold: Minimum HV Rank (default 15)
        vrp_rich_threshold: VRP level to trigger check (default 1.30)
    """

    def __init__(self, rank_threshold: float, vrp_rich_threshold: float):
        self.rank_threshold = rank_threshold
        self.vrp_rich_threshold = vrp_rich_threshold

    def is_satisfied_by(self, metrics: dict[str, Any]) -> bool:
        hv_rank = metrics.get("hv_rank")
        vrp_s = metrics.get("vrp_structural")

        # Only apply if the symbol looks "Rich"
        if vrp_s is not None and float(vrp_s) > self.vrp_rich_threshold:
            if hv_rank is not None and float(hv_rank) < self.rank_threshold:
                return False

        return True
```

### VolatilityMomentumSpec (Universal Compression)

**Single Responsibility:** "Is volatility currently collapsing across any VRP level?"

```python
class VolatilityMomentumSpec(Specification[dict[str, Any]]):
    """
    Universal compression detection (not VRP-gated).

    Rejects symbols where HV30/HV90 < 0.85 (volatility contracting).
    Complements VolatilityTrapSpec by checking momentum across ALL VRP ranges.

    Use Cases:
    - Post-earnings calm (HV30 < HV90 as recent vol drops)
    - Market regime shift (vol trending down)
    - Prevents whipsaw from trading "rich" IV when HV is collapsing

    Args:
        min_momentum_ratio: Minimum HV30/HV90 ratio (default 0.85)
            - 1.0 = HV30 equals HV90 (neutral)
            - 0.85 = HV30 is 15% below HV90 (moderate contraction, OK)
            - 0.70 = HV30 is 30% below HV90 (severe contraction, reject)

    Example:
        Symbol: XYZ
        HV30: 15%
        HV90: 25%
        Momentum: 15/25 = 0.60 (40% contraction)

        With min_momentum_ratio = 0.85:
        Result: REJECT (0.60 < 0.85) - vol collapsing too fast
    """

    def __init__(self, min_momentum_ratio: float = 0.85):
        self.min_momentum_ratio = min_momentum_ratio

    def is_satisfied_by(self, metrics: dict[str, Any]) -> bool:
        hv30 = metrics.get("hv30")
        hv90 = metrics.get("hv90")

        # Can't determine momentum - pass through
        if not hv30 or not hv90 or float(hv90) <= 0:
            return True

        try:
            momentum = float(hv30) / float(hv90)
            return momentum >= self.min_momentum_ratio
        except (ValueError, TypeError, ZeroDivisionError):
            return True  # Data error - don't reject
```

---

## Rationale

### Why Separate?

| Aspect | VolatilityTrapSpec | VolatilityMomentumSpec |
|--------|-------------------|------------------------|
| **Question** | "Is HV at yearly lows?" | "Is vol currently falling?" |
| **Timeframe** | 1-year (HV Rank) | Quarterly (HV30/HV90) |
| **VRP Gated?** | ✅ Yes (>1.30) | ❌ No (universal) |
| **Threshold** | HV Rank < 15 | HV30/HV90 < 0.85 |
| **Use Case** | Extreme situations only | Broad whipsaw protection |
| **Data Source** | HV Rank (Tastytrade) | HV30, HV90 (Tastytrade) |

### Why Different Thresholds?

**Old (Bundled):**
- Compression threshold: 0.70 (30% contraction)
- Only checked when VRP > 1.30

**New (Separated):**
- **VolatilityTrapSpec:** Still uses HV Rank < 15 (no change)
- **VolatilityMomentumSpec:** Uses 0.85 (15% contraction)

**Why gentler threshold (0.85 vs 0.70)?**

Since this is now a UNIVERSAL check (applies to all VRP levels, not just >1.30), we need a more permissive threshold to avoid over-filtering:

```
Scenario: Normal Market Conditions
HV30: 17%
HV90: 20%
Momentum: 17/20 = 0.85 (15% contraction)

Old Logic (0.70 threshold, VRP-gated):
- If VRP < 1.30: Not checked → PASSES
- If VRP > 1.30: 0.85 > 0.70 → PASSES

New Logic (0.85 threshold, universal):
- Always checked: 0.85 >= 0.85 → PASSES (boundary case)

Result: Same outcome for normal cases, better coverage for blind spot
```

---

## Consequences

### Positive

1. **Fills VRP 1.10-1.30 Blind Spot**
   ```
   Before: VRP=1.15, HV30/HV90=0.60 → ✅ PASSES (bad)
   After:  VRP=1.15, HV30/HV90=0.60 → ❌ REJECTS (good)
   ```

2. **Single Responsibility Principle**
   - Each spec has one clear job
   - Easier to test in isolation
   - Simpler to reason about

3. **Better Composability**
   ```python
   # Can now use independently
   compression_only = VolatilityMomentumSpec(0.85)

   # Or combine with other specs
   full_protection = (
       VolatilityTrapSpec(15, 1.30) &
       VolatilityMomentumSpec(0.85) &
       LiquiditySpec(...)
   )
   ```

4. **Transparent Logic**
   - User can see which check failed
   - Debugging is clearer
   - Configuration is more explicit

### Negative

1. **Slightly More Restrictive**
   - Compression check now applies to VRP 1.10-1.30 range
   - May reduce candidate count by 5-10%
   - **Mitigation:** This is the INTENDED effect (fixing blind spot)

2. **Additional Configuration**
   ```json
   {
     "volatility_trap_rank": 15,
     "volatility_trap_vrp_rich": 1.30,
     "volatility_momentum_min_ratio": 0.85  // NEW
   }
   ```

3. **Requires Filter Pipeline Update**
   - Must add VolatilityMomentumSpec to filter.py
   - Both specs need to be composed correctly
   - **Mitigation:** Clean separation makes this straightforward

---

## Alternatives Considered

### Alternative 1: Keep Bundled, Remove VRP Gate

**Proposal:** Make compression check universal but keep it in VolatilityTrapSpec

```python
# Check compression for ALL symbols (not just VRP > 1.30)
if hv30 and hv90 and float(hv90) > 0:
    if (float(hv30) / float(hv90)) < self.compression_threshold:
        return False

# Then check HV Rank only if VRP > 1.30
if vrp_s is not None and float(vrp_s) > self.vrp_rich_threshold:
    if hv_rank is not None and float(hv_rank) < self.rank_threshold:
        return False
```

**Rejected because:**
- ❌ Still violates Single Responsibility
- ❌ Harder to configure independently
- ❌ Name "VolatilityTrapSpec" becomes misleading (what does it do?)

### Alternative 2: Make VRP Gate Configurable

**Proposal:** Add parameter to control VRP gating

```python
def __init__(
    self,
    rank_threshold: float,
    compression_threshold: float,
    vrp_rich_threshold: float,
    apply_compression_universally: bool = False  # NEW
):
```

**Rejected because:**
- ❌ Adds complexity without clear benefit
- ❌ Still bundled logic (harder to test)
- ❌ Configuration becomes confusing

### Alternative 3: Three Separate Specs

**Proposal:** Split into THREE specs:
1. HVRankSpec (positional)
2. HVCompressionSpec (momentum)
3. VRPGateSpec (conditional logic wrapper)

**Rejected because:**
- ❌ Over-engineering (too granular)
- ❌ VRPGateSpec breaks Specification pattern (it's metadata, not a filter)
- ❌ Harder to understand composition

---

## Implementation

### Files Modified

1. **`src/variance/models/market_specs.py`** (lines 292-324)
   - Refactored `VolatilityTrapSpec` to remove compression logic
   - Added `VolatilityMomentumSpec` as new standalone spec

2. **`src/variance/screening/steps/filter.py`**
   - Added `VolatilityMomentumSpec` to filter composition
   - Loaded `volatility_momentum_min_ratio` from trading_rules.json

3. **`config/trading_rules.json`**
   ```json
   {
     "volatility_trap_rank": 15,
     "volatility_trap_compression": 0.70,
     "volatility_trap_vrp_rich": 1.30,
     "volatility_momentum_min_ratio": 0.85  // NEW
   }
   ```

4. **`docs/adr/0011-volatility-spec-separation.md`**
   - This document

### Migration Path

**No Breaking Changes:**
- Old config keys still work (for VolatilityTrapSpec)
- New config key is additive (volatility_momentum_min_ratio)
- Both specs applied in sequence (additive filtering)

**Rollback Procedure:**

If this causes unexpected issues:

```python
# In filter.py, comment out the new spec:
# specs.append(VolatilityMomentumSpec(momentum_ratio))

# Or set threshold to 0 (disables it):
"volatility_momentum_min_ratio": 0.0
```

---

## Testing

### Unit Tests

**File:** `tests/test_volatility_specs.py` (to be created)

```python
def test_volatility_trap_spec_positional_only():
    """VolatilityTrapSpec only checks HV Rank, not compression."""
    spec = VolatilityTrapSpec(rank_threshold=15, vrp_rich_threshold=1.30)

    # Rich VRP + low HV Rank = REJECT
    assert not spec.is_satisfied_by({
        "vrp_structural": 1.40,
        "hv_rank": 10,
        "hv30": 12,
        "hv90": 20  # Compression present but ignored
    })

    # Rich VRP + good HV Rank = PASS (even with compression)
    assert spec.is_satisfied_by({
        "vrp_structural": 1.40,
        "hv_rank": 50,
        "hv30": 12,
        "hv90": 20  # Compression present but ignored
    })

def test_volatility_momentum_spec_universal():
    """VolatilityMomentumSpec checks compression across all VRP levels."""
    spec = VolatilityMomentumSpec(min_momentum_ratio=0.85)

    # Low VRP + high compression = REJECT
    assert not spec.is_satisfied_by({
        "vrp_structural": 0.90,  # Below any threshold
        "hv30": 12,
        "hv90": 20  # 0.60 ratio < 0.85
    })

    # High VRP + high compression = REJECT
    assert not spec.is_satisfied_by({
        "vrp_structural": 1.50,  # Well above threshold
        "hv30": 12,
        "hv90": 20  # 0.60 ratio < 0.85
    })

    # Good momentum = PASS (regardless of VRP)
    assert spec.is_satisfied_by({
        "vrp_structural": 1.15,
        "hv30": 18,
        "hv90": 20  # 0.90 ratio > 0.85
    })
```

### Integration Testing

**Manual Test (TUI):**

```bash
# Before: Some symbols with VRP 1.10-1.30 + compression pass
./variance --tui

# After: Those same symbols should now be rejected
# Look for symbols with:
#   - VRP: 1.10-1.30 (in blind spot range)
#   - HV30/HV90 < 0.85 (compression present)
# Expected: Count should decrease by 5-15%
```

---

## Success Metrics

| Metric | Target | Validation |
|--------|--------|------------|
| **Candidate Count** | -5% to -15% | TUI screening run |
| **Blind Spot Coverage** | 100% | Unit tests pass |
| **Spec Independence** | Each testable alone | Unit tests for each spec |
| **Configuration Clarity** | 2 separate thresholds | JSON schema validation |
| **Whipsaw Reduction** | -3% to -5% | 30-day backtest (future) |

---

## References

- **Original Code:** `src/variance/models/market_specs.py:292-324`
- **User Request:** "each gate should be unique and standalone"
- **Related ADR:** ADR-0010 (VRP Threshold Calibration for HV90)
- **Pattern:** Specification Pattern (ADR-0002)

---

## Decision Record

**Decision Made By:** User + Claude (collaborative)
**Date:** 2025-12-25
**Rationale:** Fix VRP 1.10-1.30 blind spot, improve composability, follow Single Responsibility Principle
**Implementation Status:** 🔄 In Progress
**Testing Status:** ⏳ Pending
**Review Date:** 2026-01-15 (monitor whipsaw impact)

---

## Notes

This refactoring represents a **defensive architecture improvement** rather than a new feature. The blind spot (VRP 1.10-1.30 with collapsing volatility) was unintentional - the original intent was to protect against volatility compression, but the VRP gate limited its effectiveness.

The separation makes the codebase more maintainable and testable while providing better whipsaw protection across all VRP ranges.

---

**Related ADRs:**
- ADR-0002: Strategy Pattern
- ADR-0010: VRP Threshold Calibration for HV90

**Supersedes:** N/A (refactoring, not replacement)
**Superseded By:** TBD (future refinements)
