# RFC 002: Variance Pairs Volatility Scanner

## 1. Summary
This RFC proposes the implementation of a **Pairs Volatility Scanner** for the Variance engine. Unlike traditional equity pairs trading (which exploits *price* divergence), this system exploits **Volatility Regime Divergence** between two highly correlated assets. The goal is to identify opportunities where one asset is mechanically expensive (Rich Premium) and its correlated peer is mechanically cheap (Fair/Discount Premium), allowing for a Market-Neutral / Vol-Neutral relative value trade.

## 2. Motivation
*   **True Alpha:** Isolate "Idiosyncratic Volatility" by hedging out the broad sector/asset-class variance.
*   **Regime Independence:** Allows for trading opportunities even when the broad market is efficient or quiet, by focusing on relative mispricing.
*   **Risk Reduction:** theoretically lower beta than naked short premium strategies.

## 3. Technical Implementation

### 3.1 Configuration (`config/pairs.json`)
A strict definition of tradable pairs to ensure correlation integrity.

```json
{
  "PAIRS": [
    {"id": "PRECIOUS_METALS", "leg_a": "GLD", "leg_b": "SLV", "correlation_threshold": 0.75},
    {"id": "OIL_MAJORS", "leg_a": "XOM", "leg_b": "CVX", "correlation_threshold": 0.85},
    {"id": "SEMI_CONDUCTORS", "leg_a": "NVDA", "leg_b": "AMD", "correlation_threshold": 0.80},
    {"id": "BANKS", "leg_a": "JPM", "leg_b": "BAC", "correlation_threshold": 0.85},
    {"id": "BEVERAGES", "leg_a": "KO", "leg_b": "PEP", "correlation_threshold": 0.70}
  ]
}
```

### 3.2 The Logic (The "Spread")
We do not look at Price Spread. We look at the **VRP Spread**.

$$ \text{Spread} = \text{VRP Structural}_A - \text{VRP Structural}_B $$

*   **VRP Structural:** $IV_{30} / HV_{252}$

### 3.3 Signals
*   **CONVERGENCE:** If `Spread > 0.5` (one is 1.5x rich, the other is 1.0x fair).
*   **Action:**
    *   **Leg A (Rich):** Sell Premium (Short Strangle/Iron Condor).
    *   **Leg B (Cheap):** Buy Premium (Long Straddle/Calendar) OR No Trade (just avoiding the cheap one).

## 4. Operational Challenges
1.  **Capital Efficiency:** In standard Margin accounts, this consumes double the Buying Power (BPR) for a "hedged" return. It is extremely capital inefficient without Portfolio Margin.
2.  **Legging Risk:** Entering two complex option spreads simultaneously is difficult.
3.  **Correlation Breakdown:** If the correlation breaks (e.g., specific news on Leg A), the hedge fails, and you may lose on both volatility regimes.

## 5. Recommendation
**DEFER.** While mathematically sound, the capital inefficiency for non-PM accounts makes this a lower priority than the "Sector Divergence" approach (RFC 003), which achieves similar "Relative Value" discovery without the rigid execution requirement.
