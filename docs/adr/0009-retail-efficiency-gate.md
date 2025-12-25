# ADR 0009: Retail Efficiency Gate for Mechanical Discipline

## Status
Accepted

## Context
While the Variance engine identifies high Volatility Risk Premium (VRP), not all "rich" setups are managed equally. Retail traders, specifically those following **tastylive mechanics** (rolling for credits, managing at 21 DTE), face structural disadvantages in certain underlyings:

1.  **Friction Tax (Slippage):** In low-priced stocks, a standard $0.05 bid-ask spread represents a disproportionate percentage of the total premium. This "tax" often exceeds the expected statistical edge.
2.  **Gamma Risk:** Low-priced underlyings ($< $25) exhibit explosive Gamma. Small absolute moves in the price result in massive percentage changes in option Delta, making positions difficult to stabilize.
3.  **Mechanical Gridlock:** Rollability depends on "extrinsic value density." Low-priced stocks often have wide strike increments ($1.00 or $2.50) relative to their price. This makes rolling for a credit mathematically impossible when a strike is tested, forcing the trader to take a loss rather than extending the trade.
4.  **Binary Risk:** Stocks under $10 often trade on "liquidation premiums" rather than true VRP, reflecting bankruptcy or delisting risk rather than mean-reverting volatility.

## Decision
We will implement a hard **Retail Efficiency Gate** (`RetailEfficiencySpec`) in the screening pipeline to enforce mechanical discipline and protect capital from low-integrity setups.

### Thresholds
- **Price Floor:** Minimum **$25.00** underlying price.
- **Slippage Guard:** Maximum **5%** Bid-Ask spread relative to the option mid-price.

### Implementation
- **Specification Pattern:** A new `RetailEfficiencySpec` class in `src/variance/models/market_specs.py`.
- **Hard Filter:** This gate is applied as a bitwise AND (`&=`) in the main screening pipeline (`apply_specifications`).
- **Transparency:** Skipped symbols are tracked via `retail_inefficient_skipped_count` and displayed in the TUI diagnostic panel.

## Consequences

### Pros
1.  **Habit Enforcement:** Automatically nudges the trader toward "high-integrity" underlyings that respond predictably to standard mechanics.
2.  **Improved ROC:** By filtering out wide spreads, the engine ensures that the "Yield" shown is actually captureable, rather than being "donated" to market makers.
3.  **Reduced Tail Risk:** Higher-priced stocks generally have more liquid, dense option chains, providing better defensive "escape routes" (rolling).
4.  **Clinical Objectivity:** Rejects "story stocks" that may have high IV but poor mechanical foundations.

### Cons
1.  **Reduced Opportunity Set:** The candidate pool will shrink significantly (e.g., filtering out 200+ symbols from a 500-symbol watchlist).
2.  **Excludes Speculative Alpha:** Some high-volatility "runners" will be hidden, even if they have high VRP.

## References
- ADR 0002: Strategy Pattern for Management Logic
- ADR 0008: Multi-Provider Architecture (Tastytrade Integration)
- Quantitative Playbook: `docs/QUANT_PLAYBOOK.md`
