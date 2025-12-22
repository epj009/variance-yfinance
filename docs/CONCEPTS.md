# Variance: Quantitative Concepts Glossary

This document explains the mathematical models and systematic terminology used throughout the Variance Engine.

---

## 1. Volatility Risk Premium (VRP)
Variance treats volatility not as a "fear index," but as a mispriced insurance premium.

### VRP Structural (VRP-S)
*   **Formula:** `IV30 / HV252`
*   **Definition:** The long-term "Personality" of an asset. It measures how much the market habitually overprices risk relative to the last year of actual movement.
*   **Significance:** Assets with high VRP-S are "Natural Insurance Companies"—selling premium here is statistically profitable over long horizons.

### VRP Tactical (VRP-T)
*   **Formula:** `(IV30 - HV20) / HV20` (Markup %)
*   **Definition:** The immediate "Opportunity." It compares current pricing to the last 20 trading days (approx. 1 calendar month).
*   **Significance:** A high VRP-T indicates a short-term panic or "Richness" that is likely to mean-revert. This is the primary driver for entry timing.

---

## 2. Alpha-Theta (Expected Yield)
*   **Concept:** Standard Theta decay is a "Raw" estimate. Alpha-Theta is "Quality-Adjusted" Theta.
*   **Formula:** `Alpha-Theta = Raw Theta * (IV / HV)`
*   **Significance:** If you have $100 of Theta in a stock where VRP is 1.5, your "Alpha-Theta" is $150. You are being "overpaid" for the time you are holding the risk. Conversely, if VRP is 0.5, your $100 of Theta is only "worth" $50 statistically.

---

## 3. Regime Detection
Variance separates **Valuation** (is it expensive?) from **Regime** (is it about to move?).

### Coiled (🌀)
*   **Metric:** `HV20 / HV60 < 0.85` AND `HV20 / HV252 < 0.75`.
*   **Meaning:** Realized volatility is significantly lower than both quarterly and yearly averages. Like a compressed spring, energy is being stored.
*   **Risk:** Higher probability of a violent breakout. Range-bound trades (Iron Condors) are dangerous here.

### Expanding (⚡)
*   **Metric:** `HV20 / HV252 > 1.25`.
*   **Meaning:** The asset is currently moving 25% more than its yearly average.
*   **Trading:** Favor trend-following or respect the momentum. Mean reversion (short vol) may be "steamrolled" by the trend.

---

## 4. The Hard Gate
*   **Definition:** A safety circuit breaker in the analysis pipeline.
*   **Mechanism:** If the "North Star" (SPY) data cannot be reached or is invalid, the engine aborts the entire run.
*   **Why:** Without SPY, beta-weighting and probabilistic stress tests are meaningless. No data is safer than broken data.

---

## 5. Strict Mode Filtering
*   **Definition:** Automated hard-rejection of low-integrity data.
*   **Filters:**
    *   **Dead Legs:** Rejects equities if Call or Put ATM volume is 0.
    *   **Wide Spreads:** Rejects if slippage (spread/price) > 5%.
    *   **Lean Data:** Rejects if HV20 or IV30 are missing.
*   **Goal:** Ensure every trade recommended in the "Opportunities" list is executable at a fair price.

---

## 6. Scoring & Penalties (The "Institutional Brake")
The Variance Score (0-100) is not just a measure of richness; it is a measure of **Quality-Adjusted Opportunity**. To prevent the system from chasing dangerous "mirage" signals, two specific mechanical penalties are applied:

### The Volatility Trap Penalty (-50% Score)
*   **Metric:** `HV Rank < 15`.
*   **Definition:** Triggered when realized volatility is at its extreme bottom (bottom 15th percentile of the year).
*   **Logic:** When a stock is "dead quiet," even a tiny amount of implied volatility makes it look "Rich" (The Numerator/Denominator Artifact). 
*   **Philosophy:** Selling premium in a trap is "picking up pennies in front of a steamroller." The penalty forces the trade to the bottom of the list until realized movement returns to a normal range.

### The Compression Penalty (-20% Score)
*   **Metric:** `Regime = COILED`.
*   **Definition:** Triggered when recent movement (HV20) is significantly lower than historical averages.
*   **Logic:** A coil represents a consolidatory spring. While the VRP may look high, the risk of a gap-opening breakout is elevated.
*   **Philosophy:** Favor "Honest Vol" (Normal or Expanding regimes) where you are being paid for real, active movement, rather than just waiting for a breakout. The penalty acts as a tie-breaker, prioritizing liquid, active markets over consolidating ones.
