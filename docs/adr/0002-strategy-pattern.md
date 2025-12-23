# ADR 0002: Strategy Pattern for Trade Mechanics

## Status
Accepted

## Context
Volatility strategies (Strangles, Condors, Covered Calls) have different profit targets and defensive mechanics. Hard-coding these into a single "If/Else" block created a "God Function" that was impossible to test or extend.

## Decision
We adopted the Strategy Pattern. Each trade type is represented by a class inheriting from `BaseStrategy`. The `StrategyFactory` detects the strategy from the position data and assigns the correct object.

## Consequences
- **Pros:** New strategies (like Jade Lizards or Diagonals) can be added by creating a single file without touching the core engine.
- **Cons:** Increased abstraction layer complexity.
