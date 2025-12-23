# RFC 009: The Low Vol Trap Debate (Noise vs. Leverage)

**Date:** 2025-12-22
**Status:** DECIDED (Conservative)
**Topic:** Critical analysis of the `LOW_VOL_TRAP` filter logic.

## 1. Context
The Variance Engine employs an absolute volatility floor (`hv_floor_percent: 5.0`). This filters out assets that are "too quiet" to trade efficiently at a retail scale, even if they show a high VRP Ratio. Recent diagnostics dropped `/ZF` (HV: 3.5) and `/ZT` (HV: 1.5).

## 2. The Forum (Investment Committee)

### 🔵 Blue Team: The Efficiency Case (Signal-to-Noise)
*   **Argument:** Below 5% HV, we are trading market noise.
*   **Transaction Costs:** Small absolute moves result in small premiums ($20-$50). Slippage and commissions eat a disproportionate share of the edge (often 20%+).
*   **Attention Risk:** Trading "dead money" consumes buying power and mental bandwidth that could be used for higher-velocity opportunities.
*   **Verdict:** Keep the 5% floor to maintain a high Signal-to-Noise ratio.

### 🔴 Red Team: The Leverage Case (Stability is Safety)
*   **Argument:** Low volatility is inherently stable and safer to trade in size.
*   **Scaling:** One can synthesize a "High Vol" return by selling 10x the contracts in `/ZT` compared to a single contract in `TSLA`.
*   **Opportunity Cost:** We are excluding the entire short-end of the yield curve, which is a major source of institutional alpha.
*   **Verdict:** Lower the floor to 3% to allow 5-Year Notes and other liquid, low-vol assets.

## 3. Decision: "Safety First"
**Decision:** Maintain the **Stoic (Current)** threshold of **5.0%**.

**Rationale:**
For a $50k retail account, capital efficiency is paramount. The risk of over-leveraging comatose assets to "make them count" introduces hidden tail risk (Compressed Risk) and excessive commission drag. We will continue to focus on assets with enough natural movement to justify the transaction costs.

## 4. Current Configuration
```json
"hv_floor_percent": 5.0
```

---
*Documented by Variance (Quant Engine)*
