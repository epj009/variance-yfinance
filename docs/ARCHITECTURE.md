# Variance Architecture Map

This document outlines the design patterns used to maintain institutional-grade code quality.

## 1. Strategy Registry (The Logic Engine)
We use a dynamic **Registry Pattern**. Strategies are defined in `src/variance/strategies/` and register themselves with `BaseStrategy`.
- **How to add a strategy:** Inherit from `BaseStrategy`, use `@BaseStrategy.register("your_type")`, and the `StrategyFactory` will automatically discover it.

## 2. Market Specifications (The Alpha Filter)
The Vol Screener uses the **Specification Pattern** for modular filtering.
- **Location:** `src/variance/models/market_specs.py`
- **Composition:** Filters are combined in `vol_screener.py` using bitwise operators (`&`, `|`). This decouples "What we look for" from "How we loop through data."

## 3. Recommendation Commands (The Actions)
Portfolio triage actions are encapsulated as **Command Objects**.
- **Location:** `src/variance/models/actions.py`
- **Mandate:** Actions like `HARVEST` or `TOXIC` are rich objects that hold logic. They are **Read-Only** recommendations and never interface with brokers.

## 4. Domain Models
All core data structures (`Position`, `Portfolio`, `StrategyCluster`) are **Frozen Dataclasses**.
- **Immutability:** Once created, these objects cannot be changed. This prevents "State Drift" during complex mathematical analysis.
