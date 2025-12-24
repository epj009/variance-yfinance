# RFC 002: Pairs Volatility Scanner (Consensus Update)

## 1. Objective
Identify relative value volatility dislocations between correlated pairs of assets to capture "Spread Alpha" while remaining directional-neutral.

## 2. Quantitative Context (Consensus)
The debate on technical feasibility concluded that tick-level arbitrage is impossible with current retail data sources (yfinance). The scanner will focus on **Strategic Spread Dislocation** over a daily/weekly time horizon.

## 3. Implementation Path
### 3.1 Dynamic Pair Discovery
- **Mechanism:** Leverages **RFC 013 (Rolling Correlation Matrix)**.
- **Criteria:** Symbols are considered a "Pair" if their 60-day price correlation is $> 0.85$.
- **Scope Limiter:** To prevent computational explosion, the scanner only evaluates:
    - **Intra-Sector Pairs** (e.g., /CL vs /BZ, GLD vs SLV).
    - **Explicit Proxy Pairs** (e.g., SPY vs QQQ).

### 3.2 The Metric: Volatility Spread Z-Score
Instead of simple subtraction, we use logarithmic space to identify statistical outliers in the richness gap:
1.  **Calculate Spread:** $\text{Spread}_{t} = ln(VRP_{A} / VRP_{B})$
2.  **Calculate Z-Score:** $\text{Z} = \frac{\text{Spread}_{current} - \text{Mean}(\text{Spread}_{20d})}{\text{StdDev}(\text{Spread}_{20d})}$

### 3.3 Signal Thresholds
- **Z > 2.0:** Significant Dislocation. Sell premium in Asset A, potentially hedge in Asset B.
- **Z < -2.0:** Significant Dislocation. Sell premium in Asset B, potentially hedge in Asset A.

## 4. Architectural Constraints
- **Asynchronous Execution:** The Pairs Scan must run in a background thread to avoid blocking the main Triage Engine.
- **Synchronicity Gate:** If the data snapshots for Asset A and B are $> 30$ seconds apart, the signal is invalidated to prevent "Temporal Slippage."
- **Read-Only:** Recommendations will be output as `ActionCommand` pairs for manual entry.

## 5. Status
**Back-Burner (Verified Feasibility).** Ready for implementation phase when "Price-History Alpha" cycle commences.
