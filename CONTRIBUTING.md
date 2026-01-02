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

## Testing

Always run tests before committing:
```bash
pytest
```

