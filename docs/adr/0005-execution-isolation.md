# ADR 0005: Execution Isolation (Read-Only Mandate)

## Status
Accepted

## Context
There is a requirement to ensure the application never has the capability to execute trades or transmit orders to a broker. This is a critical safety and risk management boundary.

## Decision
The system architecture will strictly decouple **Analysis** from **Execution**. 
- The `ActionCommand` objects are "Strategic Recommendations" used solely for reporting and visualization.
- No broker API "Write" capabilities (order placement, modification, or cancellation) will be implemented in this codebase.
- The `IMarketDataProvider` and any future `IBrokerProvider` will be restricted to "Read-Only" interfaces.

## Consequences
- **Pros:** Eliminates the risk of "fat-finger" automated errors or unauthorized trading. Ensures the user is the final "Mechanical Gate" for all capital deployment.
- **Cons:** Requires the user to manually enter trades into their broker platform (Tastytrade, etc.) based on the engine's recommendations.
