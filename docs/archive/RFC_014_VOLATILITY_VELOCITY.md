# RFC 014: Volatility Velocity (The V-Trend)

## 1. Objective
Improve entry timing for premium sellers by identifying when realized volatility is decelerating (mean-reverting) rather than accelerating (expanding).

## 2. Quantitative Context
Selling premium into an accelerating volatility trend is a high-probability path to liquidation (e.g., "Catching the falling knife"). We want to sell when the "Vol Spike" has peaked.

## 3. Proposed Mechanics
### 3.1 Velocity Metric (V-Trend)
We compare the short-term realized volatility against the tactical average:
$$\text{Vol Velocity} = \frac{HV_{5} - HV_{20}}{HV_{20}}$$

- **Negative Velocity (< -0.10):** Realized movement is slowing down. The "Panic" is subsiding. Ideal entry window.
- **Positive Velocity (> 0.10):** Realized movement is accelerating. Risk of a "Vol Expansion" breakout is high.

## 4. Screener Integration
- **Gate:** Candidates with **Positive Vol Velocity** are penalized in the Variance Score.
- **Signal:** Add `⚡ (Expanding)` or `🌊 (Cooling)` icons to the Regime column in the TUI.

## 5. Status
**Proposed (High Integrity).** Derived from standard deviation of historical returns.
