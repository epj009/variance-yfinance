# Variance AI Agent Rules

## 🛡️ The Hard Mandate (Execution Isolation)
- **READ-ONLY:** This application is for analysis and decision support ONLY.
- **NO EXECUTION:** Never implement broker order transmission, trade execution, or "Write" capabilities to any financial API.
- **SAFETY GATE:** All trade recommendations must be returned as `ActionCommand` objects for user review.

## 🏛️ Architecture Patterns
- **Registry Pattern:** New strategies must be registered via `@BaseStrategy.register("type")`. Never modify `factory.py` directly to add strategies.
- **Specification Pattern:** Market filters must be implemented as `Specification` objects in `models/market_specs.py` and composed using `&`, `|`, `~`.
- **Command Pattern:** Triage actions must be encapsulated in `ActionCommand` subclasses.
- **Domain Objects:** Always use the frozen dataclasses in `models/`. Never use raw dictionaries for `Position` or `Portfolio` data.

## 🛠️ Quality Gates (Mandatory Verification)
Before suggesting a commit, you MUST run:
1. **Linter:** `ruff check . --fix`
2. **Format:** `ruff format .`
3. **Type Check:** `mypy .` (Must pass strict mode for core modules)
4. **Complexity:** `radon cc src/variance -min B` (Max complexity: 10)
5. **Tests:** `pytest`

## 📜 Documentation
- **ADRs:** Any significant architectural change requires a new Architecture Decision Record in `docs/adr/`.
- **Docstrings:** Use Google-style docstrings for all new functions/classes.