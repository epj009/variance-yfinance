# ADR 0004: Logarithmic VRP Calculation

## Status
Accepted

## Context
Volatility (IV) is not linear. A move from 20 to 30 IV is more significant than a move from 80 to 90. Raw IV/HV ratios (Linear VRP) overstate edge in high-vol environments and understate it in low-vol.

## Decision
The engine calculates VRP using logarithmic space: `log(IV / HV)`. This normalizes the "Markup" across all asset classes and volatility regimes.

## Consequences
- **Pros:** Provides a true "Alpha" signal that is comparable between a boring utility stock and a volatile crypto asset.
- **Cons:** Less intuitive for users accustomed to simple IV/HV ratios.
