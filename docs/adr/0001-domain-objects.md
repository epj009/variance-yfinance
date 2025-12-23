# ADR 0001: Domain Objects for Portfolio Data

## Status
Accepted

## Context
The initial implementation used raw Python dictionaries and CSV rows directly in the analysis logic. This created "Magic String" dependencies (e.g., `pos["Symbol"]`) and made it impossible to type-check the data flowing through the engine.

## Decision
We implemented a strict Domain Model using `src/variance/models/`. Every position is parsed into a `Position` object, and the portfolio is managed as a `Portfolio` container.

## Consequences
- **Pros:** Type safety, IDE auto-completion, and central validation logic.
- **Cons:** Slightly higher memory overhead and boilerplate for parsing.
