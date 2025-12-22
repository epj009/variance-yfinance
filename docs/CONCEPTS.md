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
