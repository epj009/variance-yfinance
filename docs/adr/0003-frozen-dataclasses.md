# ADR 0003: Immutable (Frozen) Dataclasses

## Status
Accepted

## Context
In a quantitative system, "State Drift" (accidentally changing a price or delta mid-calculation) is a silent killer. 

## Decision
All domain models and strategy configurations use Python `dataclasses` with `frozen=True`. Once a `Position` is created, it cannot be modified.

## Consequences
- **Pros:** Eliminates side-effect bugs. Objects are hashable and can be safely used in caches or sets.
- **Cons:** Requires creating a new object (using `replace()`) for every change, which can feel verbose.
