# ADR 0006: Hybrid Functional + OOP Architecture

## Status
Accepted

## Context
We need a structure that prevents "State Drift" during mathematical analysis while allowing for modular extension of trading rules.

## Decision
We adopted a **Hybrid Core**:
1.  **Functional Core:** All domain objects (`Position`, `TriageRequest`) are **Frozen Dataclasses**. Transformations return new instances rather than mutating state.
2.  **Imperative Shell:** Patterns like **Chain of Responsibility** and **Template Method** manage the orchestration of these transformations.

## Consequences
- **Pros:** 100% bug prevention for side-effects. Easy unit testing of individual pipeline steps.
- **Cons:** Slightly higher memory usage due to object copying. Requires discipline to maintain immutability.
