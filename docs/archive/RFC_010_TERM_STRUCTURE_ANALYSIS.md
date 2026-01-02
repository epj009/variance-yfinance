# RFC 010: Term Structure Analysis (The Slope Signal)

## 1. Objective
Detect Volatility Traps and differentiate between "Structural Richness" and "Binary Event Risk" by analyzing the slope of the volatility term structure.

## 2. Quantitative Context
Currently, Variance relies on a single IV point (IV30). This creates "Numerator Noise" where a high VRP might be caused by an immediate event (Earnings) rather than a mispricing of volatility.

## 3. Proposed Mechanics
### 3.1 Data Acquisition
- The `LegacyProvider` will fetch two specific points on the volatility surface:
    - **Front-Month (Near):** Target ~30 DTE.
    - **Back-Month (Next):** Target ~60 DTE.

### 3.2 The Slope Metric
We implement the **IV Ratio**:
$$\text{IV Ratio} = \frac{IV_{Near}}{IV_{Next}}$$

- **Backwardation (Ratio > 1.1):** The market is panicking about the immediate future. High probability of an "Event Trap." 
- **Contango (Ratio < 0.9):** Volatility increases with time. This is a healthy "Structural" environment for selling premium.

## 4. Triage Integration
- **Signal: EVENT:** If the symbol is in Backwardation, the triage engine should suppress the `SCALABLE` code and instead flag `EARNINGS_WARNING` or `EVENT`, even if VRP is rich.
- **Signal: HARVEST:** If a winning position enters aggressive Backwardation, the engine should prioritize the exit to avoid "Gamma Risk" near the front-month event.

## 5. Status
**Back-Burner.** Scheduled for future tactical hardening.
