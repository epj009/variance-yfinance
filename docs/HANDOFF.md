# Variance Project Handoff Documentation

**Last Updated:** December 25, 2024
**Version:** 0.1.0
**Status:** Active Development

## Executive Summary

**Variance** is a systematic volatility trading engine for retail options traders. It provides:
- **Screening:** Identifies high-probability volatility opportunities across equities and futures
- **Portfolio Analysis:** Evaluates existing positions for risk, profit potential, and rebalancing needs
- **Triage System:** Recommends specific actions (roll, close, scale, hedge) based on market conditions

**Core Philosophy:** Analysis and decision support ONLY. No automated trade execution.

## Quick Start

```bash
# 1. Clone and setup
git clone <repo-url>
cd variance-legacy provider
python3 -m venv venv
source venv/bin/activate
pip install -e ".[dev]"

# 2. Install pre-commit hooks
pre-commit install

# 3. Run tests
pytest

# 4. Run the screener
variance-screener

# 5. Run portfolio analysis
variance-analyze
```

## Project Structure

```
variance-legacy provider/
├── src/variance/              # Main application code
│   ├── models/                # Domain models (Position, Portfolio, Specs)
│   ├── strategies/            # Strategy detection (Strangle, IronCondor, etc.)
│   ├── screening/             # Volatility screening pipeline
│   │   ├── steps/             # Pipeline stages (load, filter, enrich, sort)
│   │   └── enrichment/        # Score calculation, VRP metrics
│   ├── triage/                # Portfolio analysis & recommendations
│   │   └── handlers/          # Action-specific logic (gamma, harvest, hedge, etc.)
│   ├── get_market_data.py     # Market data orchestration
│   ├── tastytrade_client.py   # Tastytrade API integration
│   └── tui_renderer.py        # Terminal UI
├── tests/                     # Test suite (64% coverage)
├── scripts/                   # Diagnostic tools
│   ├── diagnose_symbol.py     # Debug why symbols pass/fail filters
│   └── diagnose_futures_filtering.py
├── config/                    # Configuration files
│   ├── trading_rules.json     # Filter thresholds & trading parameters
│   ├── universe.json †        # [Future] Watchlist of symbols to screen
│   └── portfolio.json †       # [Future] Current positions (user-maintained)
├── watchlists/                # Current watchlist implementation
│   └── default-watchlist.csv  # Symbol watchlist (CSV format)
├── positions/                 # Current portfolio implementation
│   └── *.csv                  # Position exports from broker
└── docs/                      # Documentation
    ├── adr/                   # Architecture Decision Records
    ├── user-guide/            # End-user documentation
    └── implementation/        # Technical specs
```

**Note:** † Files marked as [Future] are aspirational JSON config files. Currently implemented as CSV files in `watchlists/` and `positions/` directories.

## Core Architecture Patterns

### 1. **Specification Pattern** (Filtering)
All market filters inherit from `Specification[T]` and support composition:

```python
# Each filter is a standalone specification
vrp_spec = VrpStructuralSpec(threshold=1.10)
vol_trap = VolatilityTrapSpec(rank_threshold=15, vrp_rich=1.30)
momentum_spec = VolatilityMomentumSpec(min_ratio=0.85)

# Compose with & (AND), | (OR), ~ (NOT)
main_spec = vrp_spec & vol_trap & momentum_spec
passed = main_spec.is_satisfied_by(market_data)
```

**Location:** `src/variance/models/market_specs.py`

### 2. **Registry Pattern** (Strategy Detection)
Strategies self-register via decorator:

```python
@BaseStrategy.register("strangle")
class Strangle(BaseStrategy):
    @classmethod
    def matches(cls, legs: list[Leg]) -> bool:
        # Detection logic
```

**Never modify** `factory.py` to add strategies. Just use the decorator.

**Location:** `src/variance/strategies/`

### 3. **Command Pattern** (Triage Actions)
All triage recommendations are `ActionCommand` objects:

```python
@dataclass(frozen=True)
class ActionCommand:
    action_type: str          # "ROLL", "CLOSE", "SCALE_UP", etc.
    symbol: str
    reason: str
    urgency: str              # "LOW", "MEDIUM", "HIGH"
    estimated_cost: float | None
    tags: list[str]
```

**Location:** `src/variance/triage/actions.py`

### 4. **Chain of Responsibility** (Triage Handlers)
Portfolio analysis flows through a chain of handlers:

```python
# Each handler checks one condition
handlers = [
    ExpirationHandler(),
    EarningsHandler(),
    GammaHandler(),
    HarvestHandler(),
    HedgeHandler(),
    # ... etc
]

# Chain processes request
for handler in handlers:
    request = handler.handle(request)
```

**Location:** `src/variance/triage/handlers/`

## Data Flow

### Screening Pipeline
```
1. Load watchlist (watchlists/default-watchlist.csv)
   ↓
2. Fetch Market Data (Tastytrade API + legacy provider)
   ↓
3. Filter (Specifications)
   ↓
4. Enrich (VRP, Scores)
   ↓
5. Sort (by score)
   ↓
6. Report (TUI or JSON)
```

### Portfolio Analysis
```
1. Parse (portfolio.json)
   ↓
2. Detect Strategies (Registry)
   ↓
3. Fetch Market Data
   ↓
4. Triage (Handler Chain)
   ↓
5. Prioritize Actions
   ↓
6. Report (TUI or JSON)
```

## Key Metrics & Calculations

### VRP (Volatility Risk Premium)
```
VRP Structural = IV / HV90
VRP Tactical   = IV / HV30 (monthly pulse)
VRP Tactical Markup = VRP Tactical - VRP Structural
```

**Why it matters:** VRP > 1.10 means options are overpriced relative to realized volatility.

### Volatility Momentum
```
Momentum Ratio = HV30 / HV90
```

**Why it matters:** Ratio < 0.85 means volatility is compressing (bad for sellers).

### IV Percentile
```
IV Percentile = Rank of current IV in 1-year range (0-100)
```

**Why it matters:** IVP < 20 means IV is near annual lows (poor selling environment).

### HV Rank
```
HV Rank = (HV252 - HV252_min) / (HV252_max - HV252_min) * 100
```

**Why it matters:** HV Rank < 15 signals potential volatility trap.

## Configuration Guide

### `config/trading_rules.json`

**Critical Thresholds:**
```json
{
  "vrp_structural_threshold": 1.10,        // Minimum VRP to sell premium
  "vrp_structural_rich_threshold": 1.30,   // VRP considered "rich"
  "hv_floor_percent": 5.0,                 // HV floor for VRP calculations
  "volatility_momentum_min_ratio": 0.85,   // Min HV30/HV90 (compression check)
  "min_iv_percentile": 20.0,               // Min IV rank
  "retail_min_price": 25.0,                // Min stock price ($)
  "hv_rank_trap_threshold": 15.0           // Positional trap trigger
}
```

**See:** `docs/user-guide/config-guide.md` for full reference.

### `config/universe.json` *(Future/placeholder)*
**Current implementation:** `watchlists/default-watchlist.csv`

Planned JSON format for watchlist symbols:
- Equities: `"AAPL"`, `"TSLA"`
- Futures: `"/ES"`, `"/CL"`, `"/ZN"`

### `config/portfolio.json` *(Future/placeholder)*
**Current implementation:** `positions/*.csv` (broker CSV exports)

Planned JSON format for current positions:
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

## Development Workflow

### Adding a New Filter

1. **Create Specification** in `src/variance/models/market_specs.py`:
```python
class MyNewSpec(Specification[dict[str, Any]]):
    def __init__(self, threshold: float):
        self.threshold = threshold

    def is_satisfied_by(self, metrics: dict[str, Any]) -> bool:
        value = metrics.get("my_metric")
        if value is None:
            return True  # Pass-through on missing data
        return float(value) >= self.threshold
```

2. **Add to Filter Pipeline** in `src/variance/screening/steps/filter.py`:
```python
my_threshold = float(rules.get("my_threshold", 10.0))
main_spec &= MyNewSpec(my_threshold)
```

3. **Add Config** to `config/trading_rules.json`:
```json
{
  "my_threshold": 10.0
}
```

4. **Write Tests** in `tests/models/test_market_specs.py`:
```python
def test_my_new_spec_passes_when_above_threshold():
    spec = MyNewSpec(threshold=10.0)
    metrics = {"my_metric": 15.0}
    assert spec.is_satisfied_by(metrics) is True
```

5. **Document** in `docs/user-guide/filtering-rules.md`

6. **Write ADR** if architectural (see `docs/adr/template.md`)

### Adding a New Strategy

1. **Create Strategy Class** in `src/variance/strategies/my_strategy.py`:
```python
from variance.strategies.base import BaseStrategy

@BaseStrategy.register("my_strategy")
class MyStrategy(BaseStrategy):
    @classmethod
    def matches(cls, legs: list[Leg]) -> bool:
        # Detection logic
        return len(legs) == 4  # Example

    def compute_breakevens(self) -> tuple[float | None, float | None]:
        # Calculation logic
        return (lower_be, upper_be)
```

2. **NO changes needed to factory.py** (registry handles it)

3. **Write Tests** in `tests/strategies/test_my_strategy.py`

### Adding a New Triage Handler

1. **Create Handler** in `src/variance/triage/handlers/my_handler.py`:
```python
from variance.triage.handler import TriageHandler

class MyHandler(TriageHandler):
    def handle(self, request: TriageRequest) -> TriageRequest:
        # Check condition
        if should_add_tag:
            request.tags.append(
                TriageTag(tag_type="MY_TAG", reason="...", urgency="MEDIUM")
            )
        return request
```

2. **Register in Chain** (`src/variance/triage/chain.py`):
```python
handlers = [
    # ... existing handlers
    MyHandler(rules),
]
```

3. **Write Tests** in `tests/triage/handlers/test_my_handler.py`

## Quality Gates (MANDATORY)

Before committing, ALL must pass:

```bash
# 1. Linter (auto-fix)
ruff check . --fix

# 2. Formatter
ruff format .

# 3. Type checker (strict mode)
mypy src/variance

# 4. Complexity (max 10)
radon cc src/variance -min B

# 5. Tests
pytest
```

**Pre-commit hooks enforce these automatically.**

### Complexity Limit
- **Max Cyclomatic Complexity:** 10 (Grade B)
- **If exceeded:** Extract helper functions or simplify logic
- **Tool:** `radon cc <file> --show-complexity`

### Type Safety
- **Strict mypy** for all `src/variance/` code
- **Exclude:** `tests/`, diagnostic scripts use `# type: ignore` headers
- **Config:** `pyproject.toml` line 63-82

## Testing Strategy

### Current Coverage: 64%

**Strong (>85%):**
- Market specifications
- Triage handlers
- Screening pipeline

**Weak (<50%):**
- Tastytrade client (14%)
- Strategy implementations (22-26%)
- Vol screener CLI (56%)

### Test Organization
```
tests/
├── models/              # Unit tests for domain models
├── strategies/          # Strategy detection tests
├── screening/           # Pipeline integration tests
├── triage/              # Triage handler tests
└── test_*.py            # Integration tests
```

### Running Tests
```bash
# All tests
pytest

# With coverage
pytest --cov=src/variance --cov-report=term-missing

# Specific marker
pytest -m unit          # Fast unit tests only
pytest -m integration   # Slower integration tests

# Exclude slow tests
pytest -m "not slow"
```

## Diagnostic Tools

### `scripts/diagnose_symbol.py`
Debug why a symbol passes or fails filters:

```bash
# Single symbol
./scripts/diagnose_symbol.py AAPL

# Multiple symbols
./scripts/diagnose_symbol.py AAPL TSLA /ES

# Check scalability of held position
./scripts/diagnose_symbol.py --held /ZN

# JSON output (for automation)
./scripts/diagnose_symbol.py --json NVDA > output.json
```

**Output:** Shows each filter result with detailed reasons.

### `scripts/diagnose_futures_filtering.py`
Specialized diagnostic for futures symbols:

```bash
./scripts/diagnose_futures_filtering.py
```

**See:** `docs/user-guide/diagnostic-tool.md` for detailed usage.

## Known Issues & Limitations

### Data Sources
1. **Tastytrade API:**
   - Primary source for IV, IV Percentile, liquidity ratings, HV30/HV90
   - Requires API credentials (not included)
   - Rate limits: Unknown (not documented)
   - Futures IV Percentile: ✅ PROVIDED for both equities and futures

2. **legacy provider (Fallback):**
   - Used for price, historical volatility
   - Rate limit: ~2000 requests/hour (market hours) / ~48 requests/hour (after hours)
   - Cache aggressively to avoid limits

### Test Failures
- 7 integration tests failing due to market data dependencies
- Tests assume market hours or cached data
- **Fix:** Mock external API calls or use fixtures

### Coverage Gaps
- Tastytrade client: 14% (major gap)
- Butterfly/TimeSpread strategies: 22-26%
- TUI renderer: 0% (expected - UI code)

### Architecture Debt
- No ScalableHandler implementation (test file removed, handler never created)
- Correlation filter exists but underutilized
- Strategy detection could be more robust (ambiguous leg matching)

## API Credentials

**Tastytrade API:**
- **NOT INCLUDED** in repository
- Expected location: `config/tastytrade_credentials.json`
- Required fields:
  ```json
  {
    "username": "...",
    "password": "...",
    "account_id": "..."
  }
  ```

**Fallback:** If credentials missing, uses legacy provider exclusively (degraded mode).

## Deployment

### Local Development
```bash
source venv/bin/activate
variance-screener        # Run screener
variance-analyze         # Run portfolio analysis
variance-tui             # Launch TUI (full interface)
```

### Production (Future)
- No production deployment currently planned
- Consider: Docker container, systemd service, cron jobs
- **Security:** Never commit API credentials

## Important Terminology

**Use consistently:**
- **Filter** (user-facing): "The VRP filter checks if IV/HV > 1.10"
- **Specification** (technical): "`VrpStructuralSpec` implements the VRP filter"
- **Screening** (process): "Run the screening pipeline to find opportunities"

**Avoid:**
- "Gate" (deprecated)
- "Check" as a noun (use "filter" instead)
- "Screen" as a noun (use "filter" or "screening")

**See:** `docs/TERMINOLOGY.md` for full guide.

## Architecture Decision Records

All significant architectural decisions documented in `docs/adr/`:

- **ADR-0001:** Specification pattern for filters
- **ADR-0002:** Registry pattern for strategies
- **ADR-0010:** HV90/HV30 methodology (vs HV252)
- **ADR-0011:** Volatility spec separation (positional vs momentum)

**Template:** `docs/adr/template.md`

## Communication Channels

**Issue Tracking:** GitHub Issues (if applicable)
**Questions:** Refer to `docs/user-guide/` first, then ask
**ADRs:** Document major decisions before implementing

## Next Steps for New Developers

1. **Read:**
   - This handoff doc
   - `docs/user-guide/filtering-rules.md`
   - `docs/adr/` (at least recent ones)

2. **Setup:**
   - Clone, install, run tests
   - Configure Tastytrade credentials (if available)
   - Run screener and analyzer

3. **Explore:**
   - Run diagnostic tools on various symbols
   - Modify watchlist (`watchlists/default-watchlist.csv`) and observe results
   - Add a test position (`positions/*.csv`) or use sample portfolio

4. **Practice:**
   - Fix a failing test
   - Improve test coverage on a weak area
   - Add a simple filter or modify a threshold

5. **Contribute:**
   - Pick from coverage gaps or known issues
   - Follow quality gates
   - Document decisions

## Support Resources

- **User Guides:** `docs/user-guide/`
- **Config Reference:** `docs/user-guide/config-guide.md`
- **Filtering Rules:** `docs/user-guide/filtering-rules.md`
- **Diagnostic Tools:** `docs/user-guide/diagnostic-tool.md`
- **ADRs:** `docs/adr/`
- **Terminology:** `docs/TERMINOLOGY.md`

---

**Questions?** Start with the docs, then ask. Most common questions are answered in the user guides.
