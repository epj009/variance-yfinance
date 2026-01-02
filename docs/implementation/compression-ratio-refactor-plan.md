# Implementation Plan: Compression Ratio Refactor

**Status:** CORRECTED - Ready for Implementation
**Date:** December 31, 2025 (Updated with Quant Research)
**Priority:** High
**Estimated Effort:** 4-6 hours
**Quant Recommendation:** Full implementation of continuous compression-based decision making

---

## ⚠️ CRITICAL CORRECTION (Dec 31, 2025)

**Original plan contained a fundamental error that was caught by user and validated by quant research.**

**THE ERROR:** Original plan recommended "STRONG BUY for compression < 0.60" (severe coiling).

**WHY IT'S WRONG:** Variance is a SHORT VOLATILITY strategy (sells premium). Severely compressed HV will mean-revert and EXPAND, causing larger realized moves that breach strikes and cause losses.

**THE FIX:** Inverted logic:
- Compression < 0.60 → AVOID (expansion risk outweighs VRP edge)
- Compression > 1.15 → STRONG BUY (vol already elevated, will contract)

**Research Evidence:** Quant agent research report (Dec 31, 2025) shows:
- Severe compression (< 0.60): 45-55% win rate for short vol
- Normal expansion (> 1.15): 70-75% win rate for short vol

See: Agent ID a26fc84 research report for full empirical validation.

---

## Executive Summary

**Goal:** Replace binary flags (`is_coiled`, `is_expanding`) with continuous Compression Ratio throughout the system.

**Impact:**
- More granular decision making (0.48 vs 0.74 compression treated differently)
- Better user visibility (TUI shows actual compression values)
- Cleaner codebase (remove redundant flag logic)
- Enhanced Vote confidence (CORRECTED: severe expansion boosts conviction, not compression)

**Key Principle:** One metric, one source of truth - use the continuous ratio directly.

---

## Phase 1: Remove Binary Flags

### 1.1 Delete Flag Creation

**File:** `src/variance/vol_screener.py:211-239`

**Current (DELETE):**
```python
# Lines 211-218
is_coiled_long = compression_ratio < 0.75
is_coiled_medium = (hv20 / hv60) < 0.85

# Line 235
"is_coiled": bool(is_coiled_long and is_coiled_medium),

# Lines 236-239
"is_expanding": bool(
    compression_ratio is not None
    and compression_ratio > rules.get("compression_expanding_threshold", 1.25)
),
```

**New (REPLACE WITH):**
```python
# No flags needed - use compression_ratio directly in decision points
# Keep other flags (is_rich, is_fair, is_earnings_soon, is_cheap)
```

**Impact:** Removes 9 lines of flag creation logic

---

### 1.2 Update Signal Logic

**File:** `src/variance/vol_screener.py:276-282`

**Current (DELETE):**
```python
if flags.get("is_rich"):
    return "RICH"

if flags["is_coiled"]:  # Ratio < 0.75
    return "BOUND"

return "FAIR"
```

**New (REPLACE WITH):**
```python
def _determine_signal_type(
    flags: dict[str, bool],
    vrp_tactical_markup: Optional[float],
    rules: dict[str, Any],
    iv_percentile: Optional[float],
    compression_ratio: Optional[float],  # NEW parameter
    hv20: Optional[float],  # NEW parameter
    hv60: Optional[float],  # NEW parameter
) -> str:
    """
    Determines signal type using continuous compression thresholds.

    Compression Zones:
    - < 0.60: COILED-SEVERE (extreme compression, high conviction)
    - 0.60-0.75: COILED-MILD (moderate compression)
    - 0.75-1.15: NORMAL
    - 1.15-1.30: EXPANDING-MILD (caution)
    - > 1.30: EXPANDING-SEVERE (avoid short vol)
    """
    # Earnings proximity (highest priority)
    if flags.get("is_earnings_soon"):
        return "EVENT"

    # VRP Rich (second priority)
    if flags.get("is_rich"):
        return "RICH"

    # Compression analysis (replaces is_coiled flag)
    if compression_ratio is not None:
        # Composite check: BOTH long-term and medium-term compression
        # (preserves the "avoid new normal low vol" logic)
        is_coiled_long = compression_ratio < 0.75
        is_coiled_medium = True
        if hv60 and hv60 > 0 and hv20:
            is_coiled_medium = (hv20 / hv60) < 0.85

        if is_coiled_long and is_coiled_medium:
            if compression_ratio < 0.60:
                return "COILED-SEVERE"
            else:
                return "COILED-MILD"

        # Expanding volatility check
        if compression_ratio > 1.30:
            return "EXPANDING-SEVERE"
        elif compression_ratio > 1.15:
            return "EXPANDING-MILD"

    # Tactical VRP (discount opportunities)
    if flags.get("is_cheap"):
        return "DISCOUNT"

    return "FAIR"
```

**Changes:**
1. Adds 3 new parameters: `compression_ratio`, `hv20`, `hv60`
2. Replaces `is_coiled` flag check with inline calculation
3. Adds severity levels (SEVERE/MILD) based on continuous threshold
4. Adds expanding detection (was orphaned `is_expanding` flag)

**Breaking Change:** Function signature changes - must update all callers

---

### 1.3 Update Signal Caller

**File:** `src/variance/screening/enrichment/vrp.py:72-76`

**Current:**
```python
candidate["Signal"] = _determine_signal_type(
    flags, candidate["vrp_tactical_markup"], rules, iv_pct_val
)
```

**New:**
```python
candidate["Signal"] = _determine_signal_type(
    flags,
    candidate["vrp_tactical_markup"],
    rules,
    iv_pct_val,
    candidate["Compression Ratio"],  # NEW
    candidate.get("hv20"),           # NEW
    candidate.get("hv60"),           # NEW
)
```

---

## Phase 2: Integrate VolatilityMomentumSpec

### 2.1 Add to Filter Pipeline

**File:** `src/variance/screening/steps/filter.py:49-74`

**Current:**
```python
# Line 49
volatility_momentum_min_ratio = float(rules.get("volatility_momentum_min_ratio", 0.85))

# Line 74 - VolatilityMomentumSpec NOT USED
main_spec &= VolatilityTrapSpec(hv_rank_trap_threshold, vrp_rich_threshold)
```

**New:**
```python
# Line 49
volatility_momentum_min_ratio = float(rules.get("volatility_momentum_min_ratio", 0.85))

# Line 74 - ADD VolatilityMomentumSpec
main_spec &= VolatilityTrapSpec(hv_rank_trap_threshold, vrp_rich_threshold)
main_spec &= VolatilityMomentumSpec(volatility_momentum_min_ratio)  # NEW
```

**Impact:** Adds hard gate filter - rejects stocks with HV30/HV90 < 0.85

**Rationale (from Quant):**
> Prevents whipsaw from trading "rich" IV when HV is collapsing. Complements VolatilityTrapSpec by checking momentum across ALL VRP ranges.

---

### 2.2 Document VolatilityMomentumSpec Purpose

**File:** `src/variance/models/market_specs.py:329` (already well-documented)

**Current docstring is EXCELLENT** - no changes needed. It already explains:
- Use cases (post-earnings calm, market regime shift)
- Threshold meanings (0.85 = 15% contraction OK)
- Example scenarios

**Action:** Reference this in user documentation

---

## Phase 3: Add Vote Logic Enhancement

### 3.1 Update Vote Calculation ⚠️ CORRECTED

**File:** `src/variance/screening/steps/report.py:103-118`

**Current:**
```python
vote = "WATCH"
if is_held:
    vote = "SCALE" if candidate.get("is_scalable_surge") else "HOLD"
elif score >= 70 and rho <= 0.50:
    vote = "BUY"
elif score >= 60 and rho <= 0.65:
    vote = "LEAN"
elif rho > 0.70:
    vote = "AVOID"
```

**New (CORRECTED FOR SHORT VOL):**
```python
vote = "WATCH"
compression = candidate.get("Compression Ratio", 1.0)

if is_held:
    vote = "SCALE" if candidate.get("is_scalable_surge") else "HOLD"
# AVOID ZONE: Severe compression (expansion risk for short vol)
elif compression < 0.60:
    vote = "AVOID (COILED)"  # Will expand, breach strikes
# REDUCE ZONE: Moderate compression (elevated risk)
elif compression < 0.75:
    if score >= 70 and rho <= 0.50:
        vote = "LEAN"  # Downgrade from BUY
    else:
        vote = "WATCH"
# STRONG BUY ZONE: Severe expansion (ideal for short vol)
elif compression > 1.30:
    if score >= 60 and rho <= 0.60:
        vote = "STRONG BUY"  # Vol will contract
    else:
        vote = "BUY"
# FAVORABLE ZONE: Mild expansion
elif compression > 1.15:
    if score >= 70 and rho <= 0.50:
        vote = "BUY"
    elif score >= 60 and rho <= 0.65:
        vote = "LEAN"
    else:
        vote = "WATCH"
# NORMAL ZONE: Standard thresholds
else:
    if score >= 70 and rho <= 0.50:
        vote = "BUY"
    elif score >= 60 and rho <= 0.65:
        vote = "LEAN"
    elif rho > 0.70:
        vote = "AVOID"
    else:
        vote = "WATCH"
```

**New Vote Logic (Corrected for Short Vol):**
- `AVOID (COILED)` - Compression < 0.60 (severe coiling, expansion risk)
- `LEAN` (downgrade) - Compression 0.60-0.75 + normal BUY criteria (elevated risk)
- `BUY` - Normal zone (0.85-1.15) with score ≥70, rho ≤0.50
- `STRONG BUY` - Compression > 1.30 (severe expansion, ideal for short vol)

**Quantitative Justification (FROM QUANT RESEARCH):**
- Compression < 0.60 → 45-55% win rate for short vol (UNFAVORABLE)
- Compression > 1.30 → 70-75% win rate for short vol (VERY FAVORABLE)
- Why: Severely compressed HV mean-reverts (expands), causing larger realized moves that breach strikes and cause gamma losses for short positions
- Why: Elevated HV contracts toward mean, supporting theta decay and reducing breach probability

---

## Phase 4: Display in TUI

### 4.1 Add Compression Column

**File:** `src/variance/tui_renderer.py:423-428`

**Current:**
```python
table.add_column("VRP_T", justify="right", width=6)
table.add_column("VRP_S", justify="right", width=6)
table.add_column("IVP", justify="right", width=5)
table.add_column("Rho", justify="right", width=5)
table.add_column("Yield", justify="right", width=7)
table.add_column("Earn", justify="right", width=5)
table.add_column("Signal", width=12)
table.add_column("Vote", justify="center", width=7)
```

**New (add Compression column):**
```python
table.add_column("VRP_T", justify="right", width=6)
table.add_column("VRP_S", justify="right", width=6)
table.add_column("Comp", justify="right", width=5)  # NEW
table.add_column("IVP", justify="right", width=5)
table.add_column("Rho", justify="right", width=5)
table.add_column("Yield", justify="right", width=7)
table.add_column("Earn", justify="right", width=5)
table.add_column("Signal", width=15)  # Wider for COILED-SEVERE
table.add_column("Vote", justify="center", width=12)  # Wider for STRONG BUY
```

---

### 4.2 Add Compression Cell Data

**File:** `src/variance/tui_renderer.py:430-490` (in the for loop)

**Add after IVP formatting:**
```python
# Compression Ratio Formatting (NEW)
comp = c.get("Compression Ratio", 1.0)
if isinstance(comp, (int, float)):
    comp_str = f"{comp:.2f}"
    # Color coding:
    # - Green: 0.85-1.15 (neutral/good momentum)
    # - Yellow: 0.60-0.85 or 1.15-1.30 (mild concern)
    # - Red: <0.60 (severe compression) or >1.30 (expanding)
    if comp < 0.60 or comp > 1.30:
        comp_style = "loss"  # Red (extreme)
    elif comp < 0.85 or comp > 1.15:
        comp_style = "warning"  # Yellow (caution)
    else:
        comp_style = "profit"  # Green (good)
    comp_display = f"[{comp_style}]{comp_str}[/]"
else:
    comp_display = "N/A"
```

**Add to table.add_row():**
```python
table.add_row(
    # ... existing columns ...
    comp_display,  # NEW (after VRP_S)
    # ... rest of columns ...
)
```

---

## Phase 5: Update Report Output

### 5.1 Add Compression to Display Dict

**File:** `src/variance/screening/steps/report.py:95-130`

**Add after Yield calculation:**
```python
# Compression Ratio (NEW)
compression = candidate.get("Compression Ratio")
if compression is not None:
    try:
        display["Compression"] = float(compression)
    except (ValueError, TypeError):
        display["Compression"] = None
else:
    display["Compression"] = None
```

**Impact:** Report JSON now includes compression field

---

## Phase 6: Update Tests

### 6.1 Update Signal Synthesis Tests

**File:** `tests/test_signal_synthesis.py`

**Current tests assume `is_coiled` flag exists - must update:**

```python
# OLD
def test_signal_coiled():
    flags = {"is_earnings_soon": False, "is_cheap": False, "is_coiled": True}
    signal = _determine_signal_type(flags, None, rules, None)
    assert signal == "BOUND"

# NEW
def test_signal_coiled_severe():
    """Severe compression (< 0.60) should return COILED-SEVERE."""
    flags = {"is_earnings_soon": False, "is_cheap": False, "is_rich": False}
    compression_ratio = 0.52  # Severe compression
    hv20 = 15.0
    hv60 = 20.0  # hv20/hv60 = 0.75 (< 0.85, medium-term compressed)

    signal = _determine_signal_type(
        flags, None, rules, None, compression_ratio, hv20, hv60
    )
    assert signal == "COILED-SEVERE"

def test_signal_coiled_mild():
    """Mild compression (0.60-0.75) should return COILED-MILD."""
    flags = {"is_earnings_soon": False, "is_cheap": False, "is_rich": False}
    compression_ratio = 0.72  # Mild compression
    hv20 = 18.0
    hv60 = 22.0  # hv20/hv60 = 0.82 (< 0.85, medium-term compressed)

    signal = _determine_signal_type(
        flags, None, rules, None, compression_ratio, hv20, hv60
    )
    assert signal == "COILED-MILD"

def test_signal_expanding_severe():
    """Expanding volatility (> 1.30) should return EXPANDING-SEVERE."""
    flags = {"is_earnings_soon": False, "is_cheap": False, "is_rich": False}
    compression_ratio = 1.45  # Severe expansion

    signal = _determine_signal_type(
        flags, None, rules, None, compression_ratio, None, None
    )
    assert signal == "EXPANDING-SEVERE"

def test_signal_composite_check():
    """Long-term compressed but medium-term normal should NOT coil."""
    flags = {"is_earnings_soon": False, "is_cheap": False, "is_rich": False}
    compression_ratio = 0.70  # Long-term compressed
    hv20 = 25.0
    hv60 = 23.0  # hv20/hv60 = 1.09 (> 0.85, NOT compressed)

    signal = _determine_signal_type(
        flags, None, rules, None, compression_ratio, hv20, hv60
    )
    assert signal == "FAIR"  # Should NOT be COILED
```

---

### 6.2 Update Vote Tests ⚠️ CORRECTED

**File:** `tests/test_vote_logic.py` (may not exist - create if needed)

```python
def test_vote_avoid_severe_compression():
    """Severe compression should trigger AVOID (expansion risk for short vol)."""
    candidate = {
        "score": 75,
        "portfolio_rho": 0.40,
        "Compression Ratio": 0.52,  # Severe compression
    }
    vote = calculate_vote(candidate, is_held=False)
    assert vote == "AVOID (COILED)"  # CORRECTED: avoid compression, not strong buy

def test_vote_strong_buy_severe_expansion():
    """Severe expansion + moderate score = STRONG BUY (ideal for short vol)."""
    candidate = {
        "score": 65,
        "portfolio_rho": 0.55,
        "Compression Ratio": 1.45,  # Severe expansion
    }
    vote = calculate_vote(candidate, is_held=False)
    assert vote == "STRONG BUY"  # CORRECTED: expansion is favorable

def test_vote_downgrade_mild_compression():
    """Mild compression should downgrade BUY to LEAN."""
    candidate = {
        "score": 72,
        "portfolio_rho": 0.45,
        "Compression Ratio": 0.68,  # Mild compression
    }
    vote = calculate_vote(candidate, is_held=False)
    assert vote == "LEAN"  # Downgraded from BUY due to compression risk
```

---

### 6.3 Update VolatilityMomentumSpec Tests

**File:** `tests/test_specs.py:155` (already exists)

**Current test is good - just verify it passes after integration:**
```python
def test_volatility_momentum_spec():
    spec = VolatilityMomentumSpec(min_momentum_ratio=0.85)

    # Pass: Normal momentum
    assert spec.is_satisfied_by({"hv30": 25.0, "hv90": 28.0})  # 0.89 ratio

    # Fail: Contracting (< 0.85)
    assert not spec.is_satisfied_by({"hv30": 20.0, "hv90": 28.0})  # 0.71 ratio
```

---

## Phase 7: Documentation

### 7.1 Update User Guide

**File:** `docs/user-guide/vrp-methodology-explained.md` (or create new section)

**Add section:**

```markdown
## Compression Ratio: Volatility Momentum Analysis ⚠️ CORRECTED

### What is Compression Ratio?

The Compression Ratio measures whether current volatility is compressed (coiling) or expanding relative to its long-term average.

**Formula:** HV30 / HV90

**Interpretation (FOR SHORT VOLATILITY STRATEGIES):**
- **< 0.60**: Severe compression - **AVOID** (expansion risk, 45-55% win rate)
- **0.60-0.75**: Mild compression - **CAUTION** (elevated risk, downgrade conviction)
- **0.75-1.15**: Normal volatility - **FAVORABLE** (standard entry, 65-70% win rate)
- **1.15-1.30**: Mild expansion - **VERY FAVORABLE** (vol likely to contract)
- **1.30+**: Severe expansion - **STRONG BUY** (ideal for short vol, 70-75% win rate)

### Why It Matters for Short Vol Strategies

Volatility exhibits **mean reversion** - periods of low vol tend to expand, and high vol tends to contract. For SHORT VOLATILITY strategies (Variance's core approach), this has CRITICAL implications:

**CRITICAL INSIGHT:** Variance SELLS premium (short gamma). We profit from theta decay and LOSE from large realized moves.

**Trading Implications (CORRECTED):**

1. **Severe Compression (< 0.60) - AVOID:**
   - HV is 40%+ below average
   - High probability of volatility EXPANSION (mean reversion)
   - Expanding HV = larger realized moves = breached strikes = losses
   - **Vote: AVOID (COILED)**
   - **Strategy:** Do not enter short vol positions; wait for expansion to occur first
   - **Why:** Move^2 relationship means 2x vol expansion = 4x gamma cost

2. **Mild Compression (0.60-0.75) - CAUTION:**
   - HV is 25-40% below average
   - Moderate expansion probability
   - **Vote: LEAN** (downgrade from BUY if criteria otherwise met)
   - **Strategy:** Reduced position sizing, wider strikes (16Δ instead of 20Δ)

3. **Severe Expansion (> 1.30) - STRONG BUY:**
   - HV is 30%+ above average
   - High probability of CONTRACTION (mean reversion toward average)
   - Contracting HV = theta works efficiently, fewer breach events
   - **Vote: STRONG BUY**
   - **Strategy:** Ideal entry for short vol; aggressive position sizing
   - **Why:** Selling premium when vol is elevated = maximum edge

### Composite Check (False Positive Prevention)

Variance uses a **two-tier compression check** to avoid flagging "new normal" low vol regimes:

1. **Long-term:** HV30/HV90 < 0.75
2. **Medium-term:** HV20/HV60 < 0.85

**Both** must be true to classify as "coiled." This prevents false signals on stocks that have permanently shifted to lower volatility.

### In the TUI (CORRECTED)

The **Comp** column shows the actual Compression Ratio:

```
Symbol | Comp  | Signal        | Vote            | Interpretation
NVDA   | 0.52  | COILED-SEVERE | AVOID (COILED)  | Expansion risk - do not enter
AMD    | 0.72  | COILED-MILD   | LEAN            | Elevated risk - caution
SPY    | 0.95  | FAIR          | BUY             | Normal regime - standard entry
QQQ    | 1.42  | EXPANDING-SEV | STRONG BUY      | Ideal for short vol - scale up
```

**Color Coding:**
- **Green (0.85-1.15):** Good momentum - favorable for short vol
- **Yellow (0.60-0.85 or 1.15-1.30):** Caution zone - monitor closely
- **Red (< 0.60):** Severe compression - AVOID (expansion risk)
- **Red (> 1.30):** Severe expansion - STRONG BUY (contraction expected)
```

---

### 7.2 Update Variance Agent Prompt ⚠️ CORRECTED

**File:** `.claude/agents/quant.md` (or wherever agent prompts are stored)

**Add to Quant Agent context:**

```markdown
## Compression Ratio (Volatility Momentum) - SHORT VOL STRATEGY

**Formula:** HV30 / HV90

**CRITICAL: Variance is a SHORT VOLATILITY strategy. Compressed HV will expand (bad), elevated HV will contract (good).**

**Critical Thresholds (CORRECTED FOR SHORT VOL):**
- < 0.60: Severe compression → **AVOID** (expansion risk, 45-55% win rate)
- 0.60-0.75: Mild compression → **CAUTION** (downgrade conviction)
- 0.75-0.85: VolatilityMomentumSpec gate (rejects if below 0.85)
- 0.85-1.15: Normal volatility → **FAVORABLE** (standard entry)
- 1.15-1.30: Mild expansion → **VERY FAVORABLE** (contraction expected)
- > 1.30: Severe expansion → **STRONG BUY** (ideal for short vol, 70-75% win rate)

**Composite Check (Coiled Detection):**
To be classified as "coiled," a stock must meet BOTH:
1. HV30/HV90 < 0.75 (long-term compression)
2. HV20/HV60 < 0.85 (medium-term compression)

This prevents false positives on stocks in "new normal" low vol regimes.

**Variance Score Impact:**
- Compression Ratio is scored via `_score_volatility_momentum()`
- Weight: 10% of total Variance Score
- Floor: 0.85, Ceiling: 1.20
- CORRECTLY penalizes compression (score → 0 when ratio < 0.85)

**Vote Impact (CORRECTED):**
- Compression < 0.60 → AVOID (COILED) - expansion risk for short vol
- Compression 0.60-0.75 → Downgrade BUY to LEAN - elevated risk
- Compression > 1.30 → STRONG BUY - ideal entry for short vol (contraction expected)
- Compression > 1.15 → BUY (if other criteria met) - favorable regime

**Filter Impact:**
- VolatilityMomentumSpec: Hard gate at 0.85 (rejects contracting vol)
- Complements VolatilityTrapSpec (VRP-gated trap detection)

**Research Evidence (Agent ID a26fc84, Dec 31 2025):**
- Severe compression (< 0.60): 45-55% win rate for short vol
- Normal regime (0.85-1.15): 65-70% win rate
- Severe expansion (> 1.30): 70-75% win rate
- Why: Move^2 relationship means 2x vol expansion = 4x gamma cost
```

---

### 7.3 Create ADR ⚠️ CORRECTED

**File:** `docs/adr/0012-compression-ratio-decision-framework.md`

```markdown
# ADR 012: Compression Ratio as Primary Decision Signal (SHORT VOL STRATEGY)

**Status:** Proposed → Accepted (2025-12-31)
**Deciders:** Quant Agent (ID a26fc84), Product Manager, User
**Date:** 2025-12-31

## ⚠️ Critical Correction

**ORIGINAL ERROR:** Initial proposal recommended "STRONG BUY for compression < 0.60" (severe coiling).

**USER CATCH:** User identified this is backwards for short vol strategies: "if we're coiled-severe wouldnt that mean our strikes get breached when it pops/expands?"

**QUANT VALIDATION:** Research confirmed user's intuition. Compression < 0.60 has 45-55% win rate for short vol (UNFAVORABLE).

**CORRECTED APPROACH:** Inverted logic - AVOID compression, STRONG BUY for expansion.

## Context

Previously, the system used binary flags (`is_coiled`, `is_expanding`) to classify volatility states. These flags discretized continuous Compression Ratio (HV30/HV90) into 3 buckets, losing granularity.

**Problem:** Two stocks with compression ratios of 0.48 and 0.74 were both labeled "COILED" despite having very different risk profiles (31% difference in compression degree).

**Additional Problem:** Binary flags did not account for Variance's SHORT VOLATILITY strategy - compressed HV is BAD (will expand), elevated HV is GOOD (will contract).

## Decision

**Replace binary flags with continuous Compression Ratio thresholds throughout the decision pipeline, CORRECTLY oriented for short volatility strategies.**

### Changes

1. **Signal Classification:**
   - OLD: `is_coiled` flag → "BOUND" signal (ambiguous)
   - NEW: Continuous thresholds with severity:
     - < 0.60 → "COILED-SEVERE" (expansion risk)
     - 0.60-0.75 → "COILED-MILD" (elevated risk)
     - > 1.30 → "EXPANDING-SEVERE" (ideal for short vol)
     - 1.15-1.30 → "EXPANDING-MILD" (favorable)

2. **Vote Enhancement (CORRECTED FOR SHORT VOL):**
   - NEW: Compression < 0.60 → "AVOID (COILED)" (expansion risk)
   - NEW: Compression 0.60-0.75 → Downgrade BUY to LEAN (elevated risk)
   - NEW: Compression > 1.30 + score ≥60 + rho ≤0.60 → "STRONG BUY" (contraction expected)
   - NEW: Compression > 1.15 + score ≥70 + rho ≤0.50 → "BUY" (favorable)

3. **Filter Integration:**
   - Activate VolatilityMomentumSpec (was orphaned)
   - Hard gate: Reject if HV30/HV90 < 0.85
   - CORRECTLY penalizes compression (aligns with short vol strategy)

4. **Display:**
   - Add "Comp" column to TUI
   - Color code (CORRECTED):
     - Green (0.85-1.15): Favorable for short vol
     - Yellow (0.60-0.85 or 1.15-1.30): Caution zones
     - Red (< 0.60): AVOID - severe compression (expansion risk)
     - Red (> 1.30): STRONG BUY - severe expansion (contraction expected)

### Preserved Logic

**Composite Coiled Check:**
- Still requires BOTH long-term (HV30/HV90 < 0.75) AND medium-term (HV20/HV60 < 0.85) compression
- Prevents false positives on "new normal" low vol stocks
- IMPORTANT: This composite check is still used to avoid "false positive" coiled signals, NOT to boost conviction

## Rationale

### Quantitative Justification (FROM QUANT RESEARCH)

1. **Mean Reversion Cuts BOTH Ways:**
   - Compression < 0.60 → 40%+ below average → WILL EXPAND (bad for short vol)
   - Expansion > 1.30 → 30%+ above average → WILL CONTRACT (good for short vol)
   - **Critical:** Same mean reversion principle, opposite implications for long vs short vol

2. **Empirical Win Rates (Short Vol Context):**
   - Severe compression (< 0.60): 45-55% win rate
   - Normal regime (0.85-1.15): 65-70% win rate
   - Severe expansion (> 1.30): 70-75% win rate
   - **Conclusion:** Short vol performs BEST when vol is already elevated

3. **Gamma Cost Quadratic Relationship:**
   - Gamma Cost ∝ (Realized Move)²
   - If HV doubles due to expansion: 2² = 4x gamma cost
   - Theta is INSUFFICIENT to cover quadrupled costs
   - **Risk Management:** Avoid compressed regimes where expansion is likely

4. **Information Content:**
   - Continuous ratio provides infinite granularity vs 3 discrete buckets
   - Users can assess conviction AND direction based on degree of compression
   - CRITICAL: Now correctly interprets compression for SHORT vol strategy

### Design Pattern Alignment

- **Single Source of Truth:** Compression Ratio used directly, no intermediate flag conversions
- **DRY Principle:** Same metric used for filters, scoring, signals, vote
- **Information Preservation:** No lossy discretization

## Consequences

### Positive

- ✅ More granular decision making (0.48 ≠ 0.74 treated differently)
- ✅ Better user visibility (TUI shows actual compression values)
- ✅ Enhanced Vote confidence (CORRECTED: expansion boosts, compression avoids)
- ✅ Cleaner codebase (no redundant flag logic)
- ✅ Completes VolatilityMomentumSpec (was orphaned)
- ✅ CORRECTLY oriented for short vol strategy (user catch prevented major error)

### Negative

- ⚠️ Breaking change to Signal types (BOUND → COILED-SEVERE/MILD)
- ⚠️ New Vote types (STRONG BUY, AVOID (COILED))
- ⚠️ Requires test updates (function signatures changed)

### Migration

**Backward Compatibility:**
- Old CSV reports with "BOUND" signal still valid (historical data)
- New reports will use "COILED-SEVERE" or "COILED-MILD"

**User Impact:**
- Users will see more specific signals (better information)
- TUI gains new Comp column (more transparency)
- CRITICAL: Vote logic now correctly handles short vol mechanics

## Alternatives Considered

### 1. Keep Binary Flags, Add Compression Display

**Pros:**
- No breaking changes
- Simpler migration

**Cons:**
- Maintains code duplication
- Vote and Signal still use coarse buckets
- Does NOT solve the short vol directional error

**Verdict:** Rejected - doesn't solve the information loss OR directional error problems

### 2. Multi-Bucket Discrete Classification

**Example:** 5 buckets (SEVERE-COILED, COILED, NORMAL, EXPANDING, SEVERE-EXPANDING)

**Pros:**
- More granular than binary
- Familiar discrete labels

**Cons:**
- Still loses continuous information
- Arbitrary bucket boundaries
- More maintenance (5 thresholds to tune)
- Still requires correct interpretation for short vol

**Verdict:** Rejected - continuous is simpler and more powerful

## References

- Quant Audit Report: `docs/analysis/compression-ratio-analysis.md`
- Quant Research Report: Agent ID a26fc84 (Dec 31, 2025)
- VolatilityMomentumSpec: `src/variance/models/market_specs.py:329`
- User Insight: "if we're coiled-severe wouldnt that mean our strikes get breached when it pops/expands?"
```

---

## Phase 8: Config Cleanup

### 8.1 Remove Orphaned Config

**File:** `config/trading_rules.json`

**Remove (if exists):**
```json
"compression_expanding_threshold": 1.25,  // DELETE - no longer used
```

**Keep:**
```json
"compression_coiled_threshold": 0.75,  // Still used for composite check
"volatility_momentum_min_ratio": 0.85,  // Now used in filter!
```

---

## Implementation Checklist

**Phase 1: Remove Binary Flags**
- [ ] Delete `is_coiled` and `is_expanding` flag creation (`vol_screener.py:211-239`)
- [ ] Update `_determine_signal_type()` signature and logic
- [ ] Update caller in `vrp.py`

**Phase 2: Integrate VolatilityMomentumSpec**
- [ ] Add to filter pipeline (`filter.py:74`)
- [ ] Verify docstring is complete

**Phase 3: Vote Enhancement**
- [ ] Add compression-based AVOID (COILED) logic
- [ ] Add compression-based STRONG BUY logic (for expansion > 1.30)
- [ ] Add downgrade logic for mild compression

**Phase 4: TUI Display**
- [ ] Add "Comp" column
- [ ] Add compression cell formatting with color coding
- [ ] Widen "Signal" and "Vote" columns

**Phase 5: Report Output**
- [ ] Add Compression to display dict

**Phase 6: Tests**
- [ ] Update signal synthesis tests (new function signature)
- [ ] Add compression-based vote tests (CORRECTED expectations)
- [ ] Verify VolatilityMomentumSpec tests pass

**Phase 7: Documentation**
- [ ] Add Compression Ratio section to user guide (CORRECTED for short vol)
- [ ] Update Variance agent prompt (CORRECTED thresholds)
- [ ] Create ADR-012 (with correction history)

**Phase 8: Cleanup**
- [ ] Remove `compression_expanding_threshold` from config (if exists)
- [ ] Verify all tests pass

---

## Testing Strategy

### Unit Tests
1. Signal synthesis with various compression values
2. Vote logic for AVOID (COILED) and STRONG BUY cases (CORRECTED)
3. VolatilityMomentumSpec filter behavior

### Integration Tests
1. Full screening pipeline with compression-based filtering
2. TUI rendering with Compression column
3. Report generation with compression field

### Manual Verification
1. Run screener on live data
2. Verify TUI displays compression values
3. Verify Signal labels match compression thresholds
4. Verify Vote logic correctly avoids compression, boosts expansion

---

## Rollback Plan

If issues arise:

1. **Git revert** to pre-refactor commit
2. **Restore binary flags** from git history
3. **Remove VolatilityMomentumSpec** from filter pipeline

**Low Risk:** Changes are isolated to decision logic, no database or API changes

---

## Success Metrics (CORRECTED)

After implementation:

1. **Code Cleanup:**
   - Removed: ~20 lines of flag logic
   - Removed: 1 orphaned config parameter
   - Added: 1 active filter (VolatilityMomentumSpec)

2. **User Visibility:**
   - TUI shows continuous compression values
   - Signal labels differentiate severity
   - Vote provides CORRECT conviction based on short vol strategy

3. **Decision Quality (CORRECTED FOR SHORT VOL):**
   - AVOID for severe compression (< 0.60) - expansion risk
   - STRONG BUY for severe expansion (> 1.30) - contraction expected
   - Filter rejects contracting vol (< 0.85) - already correct
   - Downgrade conviction for mild compression (0.60-0.75)

4. **Risk Management:**
   - Prevents entering positions when expansion probability is high
   - Boosts conviction when contraction probability is high
   - Aligns with SHORT VOLATILITY strategy mechanics

---

**Ready to implement! This plan completes the Quant's recommendation WITH CRITICAL CORRECTIONS for short vol strategy.**

**User Validation:** Implementation plan corrected based on user's insight: "if we're coiled-severe wouldnt that mean our strikes get breached when it pops/expands?"

**Quant Validation:** Empirical research (Agent ID a26fc84) confirms corrected approach.
