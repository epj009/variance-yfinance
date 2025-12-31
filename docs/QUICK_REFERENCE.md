# Variance Quick Reference

One-page cheat sheet for common tasks.

## Daily Commands

```bash
# Activate environment
source venv/bin/activate

# Run volatility screener
variance-screener

# Analyze portfolio
variance-analyze

# Launch TUI
variance-tui

# Run all tests
pytest

# Check code quality
ruff check . --fix && ruff format . && mypy src/variance
```

## File Locations

| What | Where |
|------|-------|
| Main code | `src/variance/` |
| Tests | `tests/` |
| Config | `config/trading_rules.json` |
| Watchlist | `config/universe.json` |
| Portfolio | `config/portfolio.json` |
| Docs | `docs/` |
| Diagnostic tools | `scripts/` |

## Key Configuration

**`config/trading_rules.json`** - Main thresholds:
```json
{
  "vrp_structural_threshold": 1.10,        // Min VRP to sell
  "vrp_structural_rich_threshold": 1.30,   // "Rich" VRP level
  "hv_floor_percent": 5.0,                 // HV floor for VRP calculations
  "volatility_momentum_min_ratio": 0.85,   // Min HV30/HV90
  "min_iv_percentile": 20.0,               // Min IV rank
  "retail_min_price": 25.0                 // Min stock price
}
```

## Data Sources

- **Liquidity volume**: If Tastytrade `option-volume` is available, it overrides Yahoo `atm_volume` for all symbols; Yahoo is used only when TT is missing.

## Diagnostic Tools

```bash
# Why did symbol pass/fail?
./scripts/diagnose_symbol.py AAPL

# Check multiple symbols
./scripts/diagnose_symbol.py AAPL TSLA /ES

# Check held position scalability
./scripts/diagnose_symbol.py --held /ZN

# JSON output
./scripts/diagnose_symbol.py --json NVDA > result.json

# Futures-specific diagnostic
./scripts/diagnose_futures_filtering.py
```

## Testing

```bash
# All tests
pytest

# With coverage
pytest --cov=src/variance --cov-report=term-missing

# Fast unit tests only
pytest -m unit

# Skip slow tests
pytest -m "not slow"

# Specific file
pytest tests/models/test_market_specs.py

# Specific test
pytest tests/models/test_market_specs.py::test_vrp_spec_passes

# Verbose
pytest -v

# Stop on first failure
pytest -x

# Show print statements
pytest -s
```

## Code Quality

```bash
# Lint (auto-fix)
ruff check . --fix

# Format
ruff format .

# Type check
mypy src/variance

# Complexity check
radon cc src/variance -min B

# All quality gates
ruff check . --fix && ruff format . && mypy src/variance && radon cc src/variance -min B && pytest
```

## Git Workflow

```bash
# Status
git status

# Stage changes
git add src/variance/my_file.py

# Commit (triggers pre-commit hooks)
git commit -m "feat: add new filter"

# Pre-commit hooks run:
# - ruff (lint + format)
# - mypy (type check)
# - radon-cc (complexity)

# Push
git push origin branch-name
```

## Adding Features

### New Filter
1. Create `Specification` in `src/variance/models/market_specs.py`
2. Add to pipeline in `src/variance/screening/steps/filter.py`
3. Add threshold to `config/trading_rules.json`
4. Write tests in `tests/models/test_market_specs.py`
5. Document in `docs/user-guide/filtering-rules.md`

### New Strategy
1. Create class in `src/variance/strategies/my_strategy.py`
2. Use `@BaseStrategy.register("name")` decorator
3. Implement `matches()` and `compute_breakevens()`
4. Write tests in `tests/strategies/test_my_strategy.py`
5. No factory changes needed!

### New Triage Handler
1. Create class in `src/variance/triage/handlers/my_handler.py`
2. Inherit from `TriageHandler`
3. Implement `handle(request)` method
4. Register in `src/variance/triage/chain.py`
5. Write tests in `tests/triage/handlers/test_my_handler.py`

## Metrics Reference

| Metric | Formula | Meaning |
|--------|---------|---------|
| VRP Structural | IV / HV90 | Options overpriced? |
| VRP Tactical | IV / HV20 | Short-term edge? |
| VRP Markup | VRP Tactical - VRP Structural | Edge expansion? |
| Volatility Momentum | HV30 / HV90 | Compressing (<0.85) or expanding? |
| IV Percentile | Rank in 1yr range | High (>50) or low (<20)? |
| HV Rank | (HV252-min)/(max-min)*100 | Current vs annual range |

## Filter Decision Tree

```
Symbol enters screening pipeline
  ↓
1. DataIntegrity: Has IV, HV, price?
   NO → REJECT
   YES → Continue
  ↓
2. VrpStructural: IV/HV90 >= 1.10?
   NO → REJECT (not enough edge)
   YES → Continue
  ↓
3. VolatilityTrap: If VRP>1.30, is HV Rank > 15?
   NO → REJECT (positional trap)
   YES → Continue
  ↓
4. VolatilityMomentum: HV30/HV90 >= 0.85?
   NO → REJECT (compressing vol)
   YES → Continue
  ↓
5. RetailEfficiency: Price >= $25?
   NO → REJECT (penny stock)
   YES → Continue
  ↓
6. IVPercentile: IVP >= 20?
   NO → REJECT (IV too low vs historical range)
   YES → Continue
  ↓
7. Liquidity: Rating >= 4 OR good volume/spreads?
   NO → REJECT (illiquid)
   YES → PASS ✅
```

## Architecture Patterns

| Pattern | Used For | Example |
|---------|----------|---------|
| Specification | Filters | `VrpStructuralSpec & VolatilityTrapSpec` |
| Registry | Strategies | `@BaseStrategy.register("strangle")` |
| Command | Actions | `ActionCommand(action_type="ROLL", ...)` |
| Chain of Responsibility | Triage | `handlers = [Gamma, Harvest, Hedge]` |

## Common Pitfalls

### ❌ Don't
```python
# Don't modify factory.py for strategies
# Don't use dict for domain objects
data = {"symbol": "AAPL", "price": 150}

# Don't bypass quality gates
git commit --no-verify  # Never!

# Don't mock internal logic in tests
@mock.patch('variance.models.market_specs.VrpStructuralSpec')
```

### ✅ Do
```python
# Use registry decorator
@BaseStrategy.register("my_strategy")
class MyStrategy(BaseStrategy): ...

# Use domain objects
from variance.models.position import Position
position = Position(symbol="AAPL", legs=[...])

# Run quality gates
ruff check . --fix && mypy src/variance && pytest

# Mock external dependencies
@mock.patch('variance.tastytrade_client.requests.post')
```

## Environment Variables

None currently used. All config in `config/` directory.

## File Formats

**`config/universe.json`:**
```json
["AAPL", "TSLA", "/ES", "/CL"]
```

**`config/portfolio.json`:**
```json
{
  "positions": [
    {
      "symbol": "AAPL",
      "legs": [
        {
          "option_type": "CALL",
          "strike": 150.0,
          "expiration": "2024-01-19",
          "contracts": -1,
          "premium_received": 5.0
        }
      ]
    }
  ]
}
```

## Useful Pytest Markers

```python
@pytest.mark.unit          # Fast, isolated test
@pytest.mark.integration   # Slower, multiple components
@pytest.mark.slow          # Very slow test
@pytest.mark.skipif(...)   # Conditional skip
```

Run specific markers:
```bash
pytest -m unit              # Only unit tests
pytest -m "not slow"        # Exclude slow tests
pytest -m integration       # Only integration tests
```

## Coverage Targets

| Module Type | Target |
|-------------|--------|
| Core (specs, strategies, triage) | 85%+ |
| Services (data fetching) | 70%+ |
| CLI/UI | 50%+ |
| Overall | 75%+ |

Current: 64% overall

## Dependencies

**Production:**
- yfinance (market data)
- pandas (data manipulation)
- numpy (calculations)
- rich (terminal formatting)
- scipy (statistics)

**Development:**
- pytest (testing)
- pytest-cov (coverage)
- ruff (linting + formatting)
- mypy (type checking)
- pre-commit (git hooks)

## Port Numbers / Services

None - purely local application. No web server, no database (except SQLite cache).

## API Keys Required

**Tastytrade API** (optional):
- Location: `config/tastytrade_credentials.json`
- Format: `{"username": "...", "password": "...", "account_id": "..."}`
- Fallback: yfinance if missing

## Cache Behavior

- **Location:** `.cache/` directory
- **TTL:** 24 hours
- **Size:** ~1-10 MB depending on universe
- **Clear:** `rm -rf .cache/`
- **Timezone-aware:** Skips yfinance outside market hours

## Log Levels

Currently minimal logging. Check `src/variance/variance_logger.py` for configuration.

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | General error |
| 2 | Missing config |

## Performance Benchmarks

- **Screening 100 symbols:** ~30-60 seconds (first run)
- **Screening 100 symbols:** ~5-10 seconds (cached)
- **Portfolio analysis:** ~1-5 seconds
- **Test suite:** ~4 seconds

## Memory Usage

- **Typical:** 50-100 MB
- **Peak:** 200-300 MB (large universe)

## Terminology

| Term | Definition |
|------|------------|
| Filter | User-facing: "VRP filter" |
| Specification | Technical: `VrpStructuralSpec` |
| Screening | Process: "Run screening pipeline" |
| ~~Gate~~ | Deprecated, use "filter" |
| ~~Check~~ | Deprecated, use "filter" |

See `docs/TERMINOLOGY.md` for full guide.

## Help Resources

| Question | Resource |
|----------|----------|
| How do I...? | `docs/HANDOFF.md` |
| Why isn't this working? | `docs/TROUBLESHOOTING.md` |
| What should I work on? | `docs/DEVELOPMENT_PRIORITIES.md` |
| How does filter X work? | `docs/user-guide/filtering-rules.md` |
| What does config Y do? | `docs/user-guide/config-guide.md` |
| Why was decision Z made? | `docs/adr/` |

## Emergency Commands

```bash
# Everything is broken - start over
rm -rf venv .cache __pycache__ .pytest_cache
python3 -m venv venv
source venv/bin/activate
pip install -e ".[dev]"
pre-commit install
pytest

# Pre-commit hooks failing - check locally
ruff check . --fix
ruff format .
mypy src/variance
radon cc src/variance -min B
pytest

# Screener returns nothing - diagnose
./scripts/diagnose_symbol.py AAPL TSLA

# Tests failing - run selectively
pytest -x -v  # Stop on first failure, verbose
pytest -m "not integration"  # Skip integration tests

# Can't find documentation
ls docs/
cat docs/HANDOFF.md
cat docs/TROUBLESHOOTING.md
```

---

**Print this page and keep it handy!**
