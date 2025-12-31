# Variance Troubleshooting Guide

Quick solutions to common issues.

## Installation & Setup

### Issue: `ModuleNotFoundError: No module named 'variance'`

**Cause:** Package not installed or wrong Python environment

**Solution:**
```bash
# Ensure you're in venv
source venv/bin/activate

# Install in editable mode
pip install -e ".[dev]"

# Verify
python -c "import variance; print('OK')"
```

### Issue: `pre-commit` command not found

**Cause:** Pre-commit not installed

**Solution:**
```bash
pip install pre-commit
pre-commit install
```

### Issue: Tests fail with import errors

**Cause:** Missing test dependencies

**Solution:**
```bash
pip install -e ".[dev]"  # Installs pytest, pytest-cov, etc.
```

## Running the Application

### Issue: "No cached data available" during market hours

**Cause:** First run or cache expired

**Solution:**
```bash
# Delete cache and refetch
rm -rf .cache/
variance-screener  # Will fetch fresh data
```

### Issue: "Market closed, no cache available" outside market hours

**Cause:** No cached data exists, yfinance rate limited

**Solution:**
- Run during market hours (9:30 AM - 4:00 PM EST) OR
- Use cached data from previous run (keep `.cache/` directory)

**Prevention:**
```bash
# Run once during market hours to populate cache
variance-screener

# Cache persists for 24h
```

### Issue: Screener returns 0 results

**Cause:** Filters too strict or market conditions poor

**Debug:**
```bash
# Diagnose specific symbols
./scripts/diagnose_symbol.py AAPL TSLA /ES

# Check which filter is rejecting
# Common culprits:
# - VRP too low (< 1.10)
# - IV Percentile too low (< 20)
# - Volatility compressing (HV30/HV90 < 0.85)
```

**Solution:**
- Adjust thresholds in `config/trading_rules.json`
- Add more symbols to watchlist (`watchlists/default-watchlist.csv`)
- Check market environment (low vol periods = fewer opportunities)

### Issue: Portfolio analyzer crashes with "Strategy not recognized"

**Cause:** Ambiguous leg configuration or unsupported strategy

**Debug:**
```bash
# Check portfolio CSV format
head positions/*.csv

# Verify leg counts and types match known strategies
# Strangle: 2 legs (1 call, 1 put, same DTE, different strikes)
# Iron Condor: 4 legs (2 calls, 2 puts, same DTE)
```

**Solution:**
- Fix leg configuration in position CSV file
- Add new strategy detector if needed (see HANDOFF.md)

## Testing Issues

### Issue: "ModuleNotFoundError: No module named 'variance.triage.handlers.scalable'"

**Cause:** Test file references non-existent module

**Solution:**
```bash
# Remove stale test file
rm tests/triage/handlers/test_scalable_handler.py

# Or implement the missing handler
```

### Issue: 7 integration tests failing

**Cause:** Market data dependencies, tests expect live/cached data

**Solution:**
```bash
# Skip integration tests during development
pytest -m "not integration"

# Or run during market hours with cache
variance-screener  # Populate cache first
pytest             # Then run tests
```

### Issue: "ResourceWarning: unclosed database"

**Cause:** SQLite connections not properly closed in cache

**Impact:** Low (doesn't affect functionality)

**Solution:** Known issue, see DEVELOPMENT_PRIORITIES.md #5

**Workaround:**
```bash
# Ignore warnings during testing
pytest -p no:warnings
```

### Issue: Coverage report shows 0% for some files

**Cause:** Files not imported during test run

**Solution:**
```bash
# Ensure tests actually exercise the code
pytest --cov=src/variance --cov-report=term-missing

# Check if file is excluded
cat pyproject.toml | grep exclude
```

## Pre-commit Hook Failures

### Issue: `ruff` failures

**Cause:** Code style violations

**Solution:**
```bash
# Auto-fix most issues
ruff check . --fix

# Format code
ruff format .

# Re-run hooks
git commit -m "message"
```

### Issue: `mypy` type errors

**Cause:** Type annotations missing or incorrect

**Common Fixes:**
```python
# Add type hints
def my_function(x: int) -> str:
    return str(x)

# Use Any for complex types
from typing import Any
data: dict[str, Any] = {...}

# Ignore specific lines (last resort)
result = complex_function()  # type: ignore
```

**Run manually:**
```bash
mypy src/variance
```

### Issue: `radon-cc` complexity too high

**Cause:** Function/method exceeds complexity 10

**Solution:**
- Extract helper functions
- Simplify conditional logic
- Break into smaller functions

**Check complexity:**
```bash
radon cc src/variance/my_file.py --show-complexity
```

## Configuration Issues

### Issue: "KeyError: 'vrp_structural_threshold'"

**Cause:** Config file missing required key

**Solution:**
```bash
# Validate config structure
cat config/trading_rules.json | jq '.'

# Compare with reference
cat config/trading_rules.reorganized.json
```

### Issue: Filters behaving unexpectedly

**Debug:**
```bash
# Use diagnostic tool
./scripts/diagnose_symbol.py SYMBOL

# Shows:
# - Each filter result
# - Threshold values
# - Actual metric values
# - Pass/fail reasons
```

### Issue: Futures not appearing in screener

**Cause:** Futures are subject to same filters as equities (including IV Percentile)

**Verify:**
```bash
./scripts/diagnose_symbol.py /CL /ES /GC

# Check which filters are rejecting the futures
# Common: Low IV Percentile, Low VRP, or Low Liquidity Rating
```

**Fix:** Futures must meet minimum IV Percentile threshold. If market volatility is low, fewer futures will qualify.

## Data Quality Issues

### Issue: "NaN" in IV or HV metrics

**Cause:** Insufficient price history or options data

**Solution:**
- Symbol too new (< 1 year history)
- Options not actively traded
- Remove from universe or fix data source

### Issue: VRP values seem wrong

**Debug:**
```bash
./scripts/diagnose_symbol.py SYMBOL

# Check:
# - IV value
# - HV90 value
# - VRP Structural = IV / HV90
```

**Common Causes:**
- IV from stale data
- HV calculation error
- Price discontinuity (split, dividend)

### Issue: Tastytrade API returns errors

**Error Types:**
1. **401 Unauthorized:** Check credentials in `.env.tastytrade`
2. **429 Too Many Requests:** Rate limit hit, wait and retry
3. **500 Server Error:** Tastytrade API issue, use fallback (yfinance)

**Fallback Mode:**
```bash
# Remove credentials to force yfinance-only mode
mv .env.tastytrade .env.tastytrade.bak

# Run without Tastytrade
variance-screener
```

## Performance Issues

### Issue: Screener takes >60 seconds

**Cause:** Too many symbols, API rate limits

**Solution:**
```bash
# Reduce watchlist size
# Edit watchlists/default-watchlist.csv, keep top 50-100 symbols

# Use cache during development
# Cache persists 24h, much faster
```

### Issue: High memory usage

**Cause:** Large market data cache in memory

**Solution:**
- Reduce universe size
- Clear cache periodically: `rm -rf .cache/`

## Development Issues

### Issue: Changes not reflected when running commands

**Cause:** Not installed in editable mode

**Solution:**
```bash
pip install -e .
```

### Issue: Can't find documentation

**Locations:**
- Project overview: `docs/HANDOFF.md`
- User guides: `docs/user-guide/`
- Architecture decisions: `docs/adr/`
- Config reference: `docs/user-guide/config-guide.md`
- Filtering rules: `docs/user-guide/filtering-rules.md`

### Issue: Don't understand why filter rejected symbol

**Solution:**
```bash
./scripts/diagnose_symbol.py SYMBOL

# Shows detailed breakdown:
# ✅ DataIntegrity: True
# ✅ VrpStructural: True (1.25 > 1.10)
# ❌ VolatilityMomentum: False (HV30/HV90 0.72 < 0.85)
#    Reason: Volatility compressing, risky for sellers
```

## Error Messages & Meanings

### "market_closed_no_cache"
**Meaning:** After hours, no cached data available
**Fix:** Run during market hours or use existing cache

### "insufficient_history"
**Meaning:** Symbol doesn't have 1 year of price data
**Fix:** Remove from universe or wait for more history

### "options_not_found"
**Meaning:** No options chain available for symbol
**Fix:** Symbol doesn't have listed options, remove from universe

### "data_integrity_failed"
**Meaning:** Critical data field missing (IV, HV, price)
**Fix:** Check data source, may be temporary API issue

### "ambiguous_strategy"
**Meaning:** Position legs don't match known strategy pattern
**Fix:** Verify position CSV leg configuration

## Getting Help

**Before asking:**
1. Check this troubleshooting guide
2. Read relevant docs in `docs/user-guide/`
3. Run diagnostic tools
4. Check recent ADRs for context

**When asking:**
- Include error message (full traceback)
- Show command you ran
- Show relevant config files (`config/trading_rules.json`, watchlist, positions)
- Include output from diagnostic tools

**Diagnostic checklist:**
```bash
# 1. Version info
python --version
pip list | grep variance

# 2. Config validation
cat config/trading_rules.json | jq '.'
head watchlists/default-watchlist.csv

# 3. Test run
pytest -v

# 4. Symbol diagnosis
./scripts/diagnose_symbol.py PROBLEM_SYMBOL

# 5. Quality gates
ruff check .
mypy src/variance
radon cc src/variance -min B
```

## Quick Fixes

### Reset Everything
```bash
# Nuclear option - start fresh
rm -rf venv .cache __pycache__ .pytest_cache
python3 -m venv venv
source venv/bin/activate
pip install -e ".[dev]"
pre-commit install
pytest
```

### Refresh Cache
```bash
rm -rf .cache/
variance-screener  # Refetch all data
```

### Fix Formatting
```bash
ruff check . --fix
ruff format .
```

### Regenerate Test Coverage
```bash
pytest --cov=src/variance --cov-report=html
open htmlcov/index.html  # View in browser
```

## Environment Issues

### Issue: "Python 3.9+ required"

**Solution:**
```bash
python3 --version  # Check version
# If < 3.9, install newer Python
# macOS: brew install python@3.12
# Ubuntu: sudo apt install python3.12
```

### Issue: Different results on different machines

**Causes:**
- Different Python versions (use 3.12 for consistency)
- Different timezones (affects market hours detection)
- Different cache state
- Different API credentials

**Standardize:**
```bash
# Use same Python version
python3.12 -m venv venv

# Clear cache for consistent state
rm -rf .cache/

# Use same config files
git pull  # Ensure latest config
```

---

**Still stuck?** File an issue with:
- Error message
- Steps to reproduce
- Environment (OS, Python version)
- Output from diagnostic tools
