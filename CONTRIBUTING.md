# Contributing to Variance

## Pre-Commit Quality Gates

Before committing, all code must pass:

1. **Ruff** (linting & formatting)
2. **Mypy** (type checking)
3. **Radon** (complexity analysis)

### Quick Fix Commands

**Automatic fixes:**
```bash
ruff check . --fix      # Auto-fix linting issues
ruff format .           # Format code
```

**Manual fixes needed:**
```bash
mypy .                  # Check types (must fix manually)
radon cc src/variance -min B  # Check complexity
```

### Common Mypy Errors

**Missing type annotations:**
```python
# ❌ Bad
def calculate(x):
    return x * 2

# ✓ Good
def calculate(x: float) -> float:
    return x * 2
```

**Any type issues:**
```python
# ❌ Bad  
def get_data() -> dict[str, Any]:
    ...

# ✓ Good
def get_data() -> dict[str, float | None]:
    ...
```

### Bypass Hook (Last Resort)

If existing mypy errors are in unrelated files:
```bash
git commit --no-verify -m "your message"
```

**⚠️ Use sparingly** - Fix mypy errors you introduce.

## Pre-Commit Checklist

**Run BEFORE attempting `git commit`:**

```bash
# 1. Auto-fix what you can
ruff check . --fix
ruff format .

# 2. Check types (this will fail the commit hook if errors exist)
mypy src/variance/analyze_portfolio.py  # Just check files you modified
# OR check all:
mypy .

# 3. If mypy shows errors in files you DIDN'T touch:
#    Use --no-verify (those are pre-existing issues)
# 4. If mypy shows errors in files you DID touch:
#    Fix them before committing
```

### Quick Mypy Check

To check ONLY the files you modified:
```bash
git diff --name-only | grep '\.py$' | xargs mypy
```

### Known Issues

**Files with pre-existing mypy errors** (safe to ignore with --no-verify):
- `src/variance/market_data/dxlink_client.py`
- `src/variance/market_data/pure_tastytrade_provider.py`
- `src/variance/screening/steps/filter.py`
- `src/variance/screening/pipeline.py`

If you touch these files, you may need `--no-verify` for unrelated errors.

## Testing

Always run tests before committing:
```bash
pytest
```

