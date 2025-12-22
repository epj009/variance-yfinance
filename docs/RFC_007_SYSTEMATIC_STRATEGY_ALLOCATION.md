# RFC 007: Systematic Strategy Allocation ("The Matrix") & Mechanical Validation

**Status:** Draft
**Date:** 2025-12-22
**Author:** Variance (Quant Engine)
**Context:** Upgrading the "Strategy Selection" phase from generic heuristics to rigorous, mathematically validated logic.

---

## 1. Problem Statement
The current Variance Engine (`vol_screener.py`) effectively identifies **Opportunities** (High VRP, Rich IV) but lacks the logic to systematically map them to the optimal **Mechanic** (Strategy). 

*   **Gap 1:** It recommends generic strategies (e.g., "Sell Premium") regardless of price constraints (e.g., suggesting Jade Lizards on $50 stocks where math fails).
*   **Gap 2:** It underutilizes the 22 strategies defined in `config/strategies.json`, defaulting to only 2-3 common ones (Strangle, Vertical, IC).
*   **Gap 3:** It ignores Skew (Call vs. Put IV) and Term Structure, leading to "flat" recommendations that miss directional nuance.

## 2. Proposed Solution
We propose a two-layer system upgrade:
1.  **The Validator (`util/mechanics.py`):** A physics engine that simulates trade structures on live option chains to validate mathematical feasibility (e.g., `Credit > Width`).
2.  **The Allocator (`scripts/strategy_allocator.py`):** A decision matrix that maps Market Archetypes to specific Strategy Menus.

---

## 3. Layer 1: The Validator (`mechanics.py`)
*Goal: "Don't recommend trades that don't fit the runway."*

This module accepts a `Symbol`, `Strategy`, and `Parameters` and returns `PASS/FAIL` with a Score.

### Feasibility Checks by Strategy:
*   **Jade Lizard / Big Lizard:**
    *   *Rule:* `Total_Credit > Call_Spread_Width` (Ensures Zero Upside Risk).
    *   *Failure Mode:* Low-priced stocks (<$100) often fail this due to fixed strike increments ($2.50/$5.00).
*   **Iron Condor:**
    *   *Rule:* `Credit > (1/3 * Wing_Width)` (Ensures decent Risk/Reward).
    *   *Failure Mode:* Low IV stocks offer "penny picking" risk profiles.
*   **Short Strangle:**
    *   *Rule:* `Premium_Capture_Rate > 1.5%` (Credit / Stock Price).
    *   *Rule:* `BPR < 5% Net Liq` (Size Safety).
*   **Ratio Spreads:**
    *   *Rule:* `Valley_Depth > 0` (Ensure no debit risk in the "trap" zone).

---

## 4. Layer 2: The Allocator (The "Archetypes")
*Goal: "Right Tool, Right Job."*

We define 4 Market Archetypes. The Allocator classifies each opportunity and presents a tailored menu.

### Archetype A: "The Grinder" (Income)
*   **Signal:** `[RICH]` + `[NORMAL]` + `[Neutral Skew]`
*   **Profile:** High IV, range-bound, boring.
*   **Strategy Menu:**
    *   *Beginner:* Iron Condor, Short Put Vertical.
    *   *Intermediate:* Short Strangle, Iron Fly.
    *   *Advanced:* 1-1-2 Put Ratio (The Trap).

### Archetype B: "The Spring" (Defense)
*   **Signal:** `[RICH]` + `[COILED]` (Bollinger Squeeze)
*   **Profile:** High potential for explosive move; needs upside/downside capping.
*   **Strategy Menu:**
    *   *Beginner:* Jade Lizard (No Upside Risk).
    *   *Intermediate:* Reverse Jade Lizard (No Downside Risk).
    *   *Advanced:* Broken Wing Butterfly (Directional Pin).

### Archetype C: "The Sniper" (Directional)
*   **Signal:** `[RICH]` + `[High SKEW]` (Call != Put IV)
*   **Profile:** Market is pricing a directional move.
*   **Strategy Menu:**
    *   *Bullish (Put Skew):* Bull Put Spread, ZEBRA (Stock Replacement).
    *   *Bearish (Call Skew):* Bear Call Spread, Risk Reversal.

### Archetype D: "The Shield" (Hedges)
*   **Signal:** `[DISCOUNT]` or `[CHEAP]`
*   **Profile:** Low IV; cheap to buy protection.
*   **Strategy Menu:**
    *   *Long Vol:* Calendar Spread, Diagonal Spread (PMCC).
    *   *Hedge:* Long Put Vertical.

---

## 5. Implementation Roadmap

### Phase 1: The "Physics" Engine (Foundation)
*   Create `util/greeks.py` (Black-Scholes estimator).
*   Create `util/mechanics.py` (Chain fetcher + Rule Validator).
*   *Deliverable:* A script that takes a ticker and says "Lizard: FAIL (Score 0.6), Strangle: PASS".

### Phase 2: The Data Upgrade
*   Update `get_market_data.py` to fetch **Skew** (25d Call IV vs 25d Put IV).
*   *Deliverable:* `variance_analysis.json` includes `skew_ratio`.

### Phase 3: The "Brain" Integration
*   Create `scripts/strategy_allocator.py`.
*   Integrate into `vol_screener.py` to filter output.
*   *Deliverable:* TUI shows specific strategies next to symbols (e.g., "AMZN [Lizard Viable]", "BAC [Strangle Only]").

---

## 6. Migration Strategy
*   **Backwards Compatibility:** The current `vol_screener.py` continues to work. The new system is an *additive filter*.
*   **User Impact:** Users see *fewer* generic suggestions but *higher quality* specific ones.
*   **Zero-Opp Risk:** If no strategies pass validation, the system falls back to "Raw Signal Only" to avoid silence.

---
**Decision Log:**
*   *2025-12-22:* Drafted by Variance. Validated feasibility via `research_mechanics_impact.py`. Confirmed "Price Threshold" (<$100 stocks fail Lizards) is a critical discovery.
