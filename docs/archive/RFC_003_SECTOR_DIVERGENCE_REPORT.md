# RFC 003: Sector Divergence Reporting

## 1. Summary
This RFC proposes an enhancement to the existing `vol_screener.py` to generate a **Sector Divergence Report**. Instead of defining rigid pairs, this system aggregates scan results by Sector (e.g., "Energy", "Financials") to calculate a "Sector Mean Volatility Bias." It then highlights individual symbols that deviate significantly from their sector's average regime.

## 2. Motivation
*   **Organic Discovery:** Finds relative value trades dynamically without maintaining a rigid "Pairs" list.
*   **Contextual Analysis:** Helps the user understand if a symbol is expensive because *it* is special, or if the *entire sector* is bidding up volatility (Systematic vs Idiosyncratic risk).
*   **Filtering:** Allows the user to avoid "False Positives" (e.g., if all Banks are "Rich", selling JPM is a Sector Bet, not a relative value bet).

## 3. Technical Implementation

### 3.1 Aggregation Logic
Modify `vol_screener.py` to perform a post-scan pass:

1.  **Group By Sector:** Collect all `VRP Structural` (Vol Bias) scores for symbols in "Financial Services".
2.  **Calculate Sector Mean:** $\mu_{sector} = \frac{\sum VRP}{N}$
3.  **Calculate Deviation:** $\Delta_{sym} = VRP_{sym} - \mu_{sector}$

### 3.2 The Report Output
Add a new section to the TUI / JSON output:

```text
SECTOR DIVERGENCE (Financial Services)
Avg VRP: 1.15 (Sector is Elevated)

1. JPM  | VRP: 1.45 | Delta: +0.30 (Expensive relative to Peers) -> SELL CANDIDATE
2. WFC  | VRP: 1.15 | Delta:  0.00 (In line)
3. C    | VRP: 0.85 | Delta: -0.30 (Cheap relative to Peers)     -> BUY CANDIDATE
```

### 3.3 Strategy Implication
*   **Dispersion Lite:** The user can intuitively choose to Sell Vol on JPM and Buy Vol on C to construct a pseudo-pair.
*   **Best-in-Class Selection:** If the user wants to get Short Financials, they should mechanically choose the asset with the highest positive Delta (JPM) rather than a random pick.

## 4. Operational Considerations
*   **Data Density:** Requires scanning a sufficient number of symbols per sector to be statistically significant (min 3-5 symbols).
*   **Watchlist Expansion:** We may need to expand `default-watchlist.csv` to ensure we have "clusters" of assets rather than isolated picks.

## 5. Recommendation
**ADOPT.** This is a high-impact, low-effort enhancement. It leverages existing data to provide deeper strategic context ("So What?") without requiring complex new execution mechanics. It aligns perfectly with the "Variance" philosophy of statistical triage.
