# Ruff Lint Violations Report
**Generated:** 2025-12-23
**Status:** 68 violations remaining (8 auto-fixed, 16 files reformatted)

## Summary by Category

| Category | Count | Auto-Fixable | Priority |
|----------|-------|--------------|----------|
| E701 - Multiple statements on one line | 32 | No | Medium |
| E722 - Bare except clauses | 5 | No | High |
| E402 - Module import not at top | 3 | No | Low |
| SIM102/105/116/117 - Code simplification | 28 | No | Low |

## High Priority: Bare Except Clauses (E722)

**Risk:** Catches all exceptions including KeyboardInterrupt and SystemExit, making debugging difficult.

### scripts/research_liquidity_compare.py
- Line 60: `except:` → should be `except Exception:`
- Line 64: `except:` → should be `except Exception:`
- Line 73: `except:` → should be `except Exception:`
- Line 93: `except:` → should be `except Exception:`

### scripts/research_mechanics_impact.py
- Line 59: `except:` → should be `except Exception:`

**Recommendation:** Fix these before production use. Research scripts can remain as-is for now.

---

## Medium Priority: Single-Line Statements (E701)

**Impact:** Reduces code readability, violates PEP 8 style guidelines.

### Core Modules (Fix Soon)
- `src/variance/get_market_data.py:108` - `if value is None: return`
- `src/variance/get_market_data.py:128` - `if i == retries - 1: raise e`
- `src/variance/get_market_data.py:133` - `if not raw_symbol: return None`
- `src/variance/get_market_data.py:134` - `if raw_symbol in SYMBOL_MAP: return ...`
- `src/variance/triage_engine.py:270` - `if max_val == 0: max_val = 1.0`
- `src/variance/triage_engine.py:374-376` - Multiple `if X: reasons.append(...)`
- `src/variance/triage_engine.py:431` - `if val is None: return "$0.00"`
- `src/variance/triage_engine.py:435` - `if val is None: return "0.0%"`

### Research Scripts (Low Impact)
- `scripts/research_integrity_impact.py:45`
- `scripts/research_liquidity_compare.py` (multiple)
- `scripts/research_mechanics_impact.py` (multiple)
- `scripts/research_proxy_bake_off.py:92`

**Recommendation:** Fix core modules in next cleanup pass. Research scripts can remain as-is.

---

## Low Priority: Code Simplification (SIM)

These are style suggestions that don't affect correctness:

### SIM102 - Nested if → single if with 'and'
- `src/variance/common.py:79` - Can combine two nested ifs
- `src/variance/triage_engine.py:502` - Can combine two nested ifs

### SIM105 - try/except/pass → contextlib.suppress
- `src/variance/diagnose_screener.py:144` - Use `contextlib.suppress(ValueError)`

### SIM116 - if/elif chain → dictionary
- `src/variance/vol_screener.py:181` - Signal type mapping could be a dict

### SIM117 - Nested with → single with
- `tests/test_vrp_tactical_floor.py:390` - Combine context managers

**Recommendation:** Ignore for now. These are minor style improvements.

---

## Low Priority: Import Order (E402)

Module-level imports not at top of file:

- `src/variance/analyze_portfolio.py:22` - Import after constants
- `src/variance/get_market_data.py:33` - Import after config dict
- `tests/test_analyze_portfolio.py:136` - Import in middle of file

**Recommendation:** Fix if refactoring those files. Not critical.

---

## Pre-Commit Status

✅ **Installed:** `.pre-commit-config.yaml` created
✅ **Active:** Git hooks installed at `.git/hooks/pre-commit`
✅ **Coverage:** Ruff lint + format runs on all Python files

### Commands:
```bash
# Run manually on all files
./venv/bin/pre-commit run --all-files

# Run on staged files (happens automatically on commit)
git commit

# Update hook versions
./venv/bin/pre-commit autoupdate
```

---

## Recommended Action Plan

### Phase 1: Critical (Before Production)
- [ ] Fix 5 bare except clauses in research scripts
- [ ] Review E722 patterns in core modules (if any added)

### Phase 2: Cleanup (Next Refactor)
- [ ] Fix single-line statements in core modules (8 instances)
- [ ] Fix import order violations (3 instances)

### Phase 3: Polish (Optional)
- [ ] Apply SIM simplifications if desired
- [ ] Clean up research scripts style

---

## Git Workflow

Pre-commit hooks will now **automatically**:
1. Run `ruff check --fix` on staged files
2. Run `ruff format` on staged files
3. Block commits if unfixable violations remain

**Note:** Most violations are in research scripts, which don't block commits.
