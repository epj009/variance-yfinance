# RFC 013: Rolling Correlation Matrix (Diversification Guard)

## 1. Objective
Protect the portfolio from "Macro Correlation Traps" where multiple positions that appear distinct move in lockstep during a volatility event.

## 2. Quantitative Context
Standard sector classification (e.g., "Financials" vs "Energy") is often insufficient during regime shifts. Assets like Gold (GLD) and Currencies (/6A) can temporarily correlate to 0.8+, turning a "Diversified" portfolio into a single, massive directional bet.

## 3. Proposed Mechanics
### 3.1 Pairwise Correlation
Calculate the **Pearson Correlation Coefficient** of log returns for all symbols:
- **Tactical Window:** 20-day rolling window.
- **Structural Window:** 60-day rolling window.

### 3.2 Dynamic Filtering
Before adding a candidate to the "Opportunities" list, the engine checks its correlation against the **Weighted Portfolio Mean**:
- **Condition:** $\rho_{\text{Candidate, Portfolio}} < 0.70$

## 4. TUI Integration
- **The Engine (Mix):** Update the "Mix" status from simple sector counts to a **Correlation Heatmap** summary.
- **Warning:** Flag `[CONCENTRATED]` if the average pairwise correlation of the portfolio exceeds 0.65.

## 5. Status
**Proposed (High Integrity).** Relies on pure historical return math.
