# RFC 008: The HV Rank Trap Debate (Risk vs. Alpha)

**Date:** 2025-12-22
**Status:** PROPOSED / DOCUMENTED
**Topic:** Critical analysis of the `HV_RANK_TRAP` filter logic.

## 1. Context
The Variance Engine currently employs a filter that drops symbols if they exhibit "Rich VRP" (IV > HV) but "Low HV Rank" (< 15.0). Recent diagnostics showed that nearly all Bond products (`/ZN`, `/ZB`, `/ZF`) were excluded by this filter.

## 2. The Forum (Investment Committee)

### 🔵 Blue Team: The Risk Case (Mean Reversion)
*   **Argument:** Volatility is mean-reverting. Trading at an HV Rank of 0.5 maximizes **Realized Volatility Expansion Risk**.
*   **Convexity:** At low ranks, we have "Negative Vega Convexity." A return to normal volatility levels will cause position value to inflate (loss) even if the underlying price remains static.
*   **Fragility:** Low HV environments lead to strikes being physically closer to the money (ATM). This increases **Gamma Risk**, leaving no room for error if the asset moves.
*   **Verdict:** Keep the trap to ensure we only sell premium when we are "paid for the volatility risk," not just the "price movement risk."

### 🔴 Red Team: The Alpha Case (The Edge is the Spread)
*   **Argument:** Alpha comes from the **Spread (VRP)**, not the **History (Rank)**. 
*   **Mathematical Edge:** If Implied Vol is 10% and Realized Vol is 5%, the statistical edge is 100% markup. Rejecting this because "it was 20% last year" is a narrative fallacy.
*   **Clustering:** Volatility clusters. Low vol often stays low for extended periods. Filtering it out results in "Theta Starvation."
*   **Verdict:** Abolish or lower the trap. If the market is overpricing the move *today*, we should take the trade.

## 3. Mathematical Reconciliation
The current logic is binary:
`IF (VRP > Rich) AND (Rank < 15) THEN -> DROP`

### The "Fragility" Equation
A position is fragile when:
$$\text{Premium Received} < \text{Potential Vega Loss (1SD Expansion)}$$

In `/ZN` (Rank 0.5), the premium is historically low. A jump to Rank 20 would wipe out weeks of Theta in seconds.

## 4. Proposed Configuration Adjustments

| Strategy | `hv_rank_trap_threshold` | Outcome |
| :--- | :--- | :--- |
| **Stoic (Current)** | `15.0` | High safety, avoids Bond expansion traps. |
| **Aggressive** | `5.0` | Allows "Relatively Cheap" but "Mathematically Rich" trades. |
| **Pure Quant** | `0.0` | Ignores history entirely; trades only the current VRP. |

## 5. Next Steps
*   Monitor `/ZN` and `/ZB` performance. If Vol remains low while they remain "Rich," the Red Team's argument for "lost opportunity" gains weight.
*   Consider a "Dynamic Trap" that scales based on the *magnitude* of the VRP markup (e.g., if VRP > 2.0, ignore the Rank Trap).

---
*Documented by Variance (Quant Engine)*