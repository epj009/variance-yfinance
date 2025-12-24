# RFC 020: Macro Correlation Guard (Statistical Diversification)

## 1. Objective
Quantify the "True Diversification" of the portfolio by measuring the statistical lockstep of held positions. Move beyond Sector Labels (metadata) to Pearson Correlation (math).

## 2. Quantitative Context
Sector labels are lagging indicators. In a "risk-off" event, correlations converge to 1.0. A portfolio holding AAPL, MSFT, and NVDA is 90% correlated, meaning it is effectively one single large position.

## 3. Proposed Mechanics
### 3.1 Average Pairwise Correlation ($\bar{\rho}$)
For all held positions $N$, calculate the average of all unique pairwise Pearson coefficients:
$$\bar{\rho} = \frac{2}{N(N-1)} \sum_{i < j} \rho_{i,j}$$

### 3.2 Concentration Thresholds
- **DIVERSIFIED:** $\bar{\rho} < 0.40$ (Clinical Ideal)
- **BOUND:** $0.40 \le \bar{\rho} < 0.65$ (Normal Market)
- **CONCENTRATED:** $\bar{\rho} \ge 0.65$ (Macro Trap - Alert Triggered)

## 4. TUI Integration
- **The Engine (Mix):** Replace the static "Mix" status with a dynamic Correlation metric.
- **Alerting:** If $\bar{\rho} > 0.65$, inject a `[CONCENTRATED]` warning into the Capital Console.

## 5. Status
**PROPOSED.** Infrastructure (CorrelationEngine) is already live.
