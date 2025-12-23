# Contributing to Variance

## The Philosophy
Variance is a systematic volatility engine. We value **Occurrences**, **Probabilities**, and **Mechanics**.

### Core Mandates
1. **Trade Small:** Keep functions under 10 complexity points (Radon).
2. **Trade Math:** Use logarithmic space for volatility comparisons.
3. **No Side Effects:** Domain objects MUST be frozen dataclasses.
4. **Read-Only Engine:** This application is for analysis and decision support only. It MUST NEVER implement trade execution or order transmission logic.

## Adding a New Strategy
1. Create a new class in `src/variance/strategies/`.
2. Inherit from `BaseStrategy` or `ShortThetaStrategy`.
3. Define the `detect()` method to identify the strategy from position legs.
4. Add the strategy to the `StrategyFactory`.
5. Update `config/strategies.json` with the relevant profit targets.

## Quality Gates
Before submitting a PR, ensure:
- `ruff check .` passes.
- `mypy .` passes (no type errors).
- All tests in `tests/` are green.
- You have documented the change in an ADR if it alters core logic.
