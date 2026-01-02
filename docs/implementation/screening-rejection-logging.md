# Screening Rejection Logging Enhancement

## Problem Statement

Current state:
- ✅ `--debug` flag shows rejection reasons on console
- ✅ `debug_rejections` dict tracked in `ScreeningContext`
- ❌ **NOT logged to files** - impossible to troubleshoot production runs after they complete
- ❌ No searchable audit trail of why symbols failed filters

**User Requirement:** "verbose output as to why each symbol failed, which is required information when troubleshooting our pipelines"

---

## Solution: Dedicated Screening Audit Log

### Log File: `logs/variance-screening.log`

**Purpose:** Detailed per-symbol filter results for troubleshooting

**Retention:** 30 days (daily rotation)

**Content:**
```
2026-01-01 13:45:24.123 | INFO | variance.screening.filter:205 | [session:sess_20260101_134523_a1b2] REJECTED | TSLA | IV Percentile: 13.7 < 50.0
2026-01-01 13:45:24.124 | INFO | variance.screening.filter:205 | [session:sess_20260101_134523_a1b2] REJECTED | /6E | Vol Momentum: 0.72 < 0.85
2026-01-01 13:45:24.125 | INFO | variance.screening.filter:205 | [session:sess_20260101_134523_a1b2] REJECTED | QQQ | Yield: 3.21% < 4.00%
2026-01-01 13:45:24.126 | INFO | variance.screening.filter:249 | [session:sess_20260101_134523_a1b2] REJECTED | AAPL | Liquidity: volume 450 < 500
2026-01-01 13:45:24.127 | INFO | variance.screening.filter:180 | [session:sess_20260101_134523_a1b2] ACCEPTED | /NG | Passed all filters
2026-01-01 13:45:24.128 | INFO | variance.screening.filter:180 | [session:sess_20260101_134523_a1b2] ACCEPTED | SPY | Passed all filters
```

**Grep Examples:**
```bash
# Find all rejections for a specific symbol
grep "TSLA" logs/variance-screening.log | grep REJECTED

# Find all yield rejections
grep "Yield:" logs/variance-screening.log

# Find all rejections in a specific session
grep "sess_20260101_134523_a1b2" logs/variance-screening.log | grep REJECTED

# Count rejection reasons
grep REJECTED logs/variance-screening.log | cut -d'|' -f5 | cut -d':' -f1 | sort | uniq -c
```

---

## Implementation

### Step 1: Add Logger to `filter.py`

**Location:** `src/variance/screening/steps/filter.py` (top of file)

```python
import logging

logger = logging.getLogger(__name__)
```

### Step 2: Log Rejections as They Happen

**Option A: Log in `apply_specifications()` after rejection tracking**

**Location:** `src/variance/screening/steps/filter.py:205` and `:249`

```python
# Around line 205 (inside loop where rejections[sym] = reason)
if rejections is not None:
    rejections[sym] = reason
    # NEW: Log rejection immediately
    logger.info("REJECTED | %s | %s", sym, reason)

# Around line 249 (portfolio correlation rejection)
rejections[symbol] = reason
# NEW: Log rejection
logger.info("REJECTED | %s | %s", symbol, reason)
```

**Option B: Log accepted symbols too (for complete audit trail)**

```python
# When symbol passes all filters (add to candidates list)
logger.info("ACCEPTED | %s | Passed all filters", symbol)
```

### Step 3: Add Screening Log Handler to Logging Config

**Location:** `src/variance/logging_config.py` (or wherever logging is configured)

```python
def setup_logging(session_id: str, debug: bool = False):
    """Configure all log handlers."""

    # ... existing handlers ...

    # NEW: Screening-specific log
    screening_handler = TimedRotatingFileHandler(
        filename="logs/variance-screening.log",
        when="midnight",
        interval=1,
        backupCount=30,  # 30 days retention
        encoding="utf-8",
    )
    screening_handler.setLevel(logging.INFO)
    screening_handler.setFormatter(standard_formatter)

    # Attach ONLY to screening.steps modules
    screening_logger = logging.getLogger("variance.screening.steps")
    screening_logger.addHandler(screening_handler)
    screening_logger.setLevel(logging.INFO)
```

### Step 4: Session ID Injection

**Already implemented** in professional logging plan - ensures all logs have `[session:XXX]` prefix for correlation.

---

## Alternative: Summary Logging (Less Verbose)

If per-symbol logging is too verbose, log summary after filtering:

**Location:** `src/variance/screening/pipeline.py:75` (after `_filter_candidates()`)

```python
def _filter_candidates(self) -> None:
    """Step 3: Apply specifications (Hook)."""
    from .steps.filter import apply_specifications

    debug_rejections = {} if getattr(self.ctx.config, "debug", False) else None
    self.ctx.candidates, self.ctx.counters = apply_specifications(
        self.ctx.raw_data,
        self.ctx.config,
        self.ctx.config_bundle.get("trading_rules", {}),
        self.ctx.config_bundle.get("market_config", {}),
        portfolio_returns=self.ctx.portfolio_returns,
        rejections=debug_rejections,
    )
    if debug_rejections is not None:
        self.ctx.debug_rejections = debug_rejections

        # NEW: Log rejection summary
        logger.info("Filter rejections: %d symbols rejected", len(debug_rejections))
        for symbol, reason in sorted(debug_rejections.items()):
            logger.info("REJECTED | %s | %s", symbol, reason)
```

**Pros:**
- ✅ All rejection data in one place in the log
- ✅ Easy to correlate with session
- ✅ Less scattered logging

**Cons:**
- ❌ Only logged if `--debug` flag is set
- ❌ Not logged in real-time during filtering

---

## Recommendation

**Use Option A (Log as rejections happen) + Always enable rejection tracking**

**Changes needed:**

1. **Remove `--debug` requirement for rejection tracking:**

```python
# In pipeline.py:116 - BEFORE
debug_rejections = {} if getattr(self.ctx.config, "debug", False) else None

# AFTER - Always track rejections for logging
debug_rejections = {}
```

2. **Add logging calls in filter.py:**

```python
# Add at rejection points
if rejections is not None:
    rejections[sym] = reason
    logger.info("REJECTED | %s | %s", sym, reason)
```

3. **Add `logs/variance-screening.log` handler** to logging config

**Result:**
- ✅ Every screening run logs all rejections to file
- ✅ Searchable with grep/awk/etc
- ✅ Session-correlated for troubleshooting
- ✅ 30-day retention
- ✅ No performance impact (logging is fast)

---

## Testing

```bash
# Run screener
./screen 50

# Check screening log
tail -f logs/variance-screening.log

# Verify session ID in logs
grep "sess_" logs/variance-screening.log | head -1

# Count rejections by reason
grep REJECTED logs/variance-screening.log | cut -d'|' -f4 | sort | uniq -c | sort -rn
```

**Expected Output:**
```
     15 Yield: no option pricing available
     12 IV Percentile: < 50.0
      8 Liquidity: volume < 500
      5 Vol Momentum: < 0.85
      3 VRP Tactical: <= 1.00
```

---

## Performance Impact

**Negligible:**
- Logging is buffered I/O
- File writes happen asynchronously
- ~0.1ms per log statement
- 50 symbols × 0.1ms = 5ms total overhead
- Acceptable for screening runs

---

## Migration Path

1. **Phase 1:** Add logger to `filter.py`, add log calls (2 hours)
2. **Phase 2:** Add screening log handler to logging config (1 hour)
3. **Phase 3:** Test with real screening runs (1 hour)
4. **Phase 4:** Remove `--debug` requirement for rejection tracking (30 min)

**Total Effort:** ~4.5 hours

---

## Success Criteria

✅ Every screening run logs rejections to `logs/variance-screening.log`
✅ Logs include session ID for correlation
✅ Logs include symbol and specific rejection reason
✅ Logs are searchable with standard Unix tools (grep, awk, etc.)
✅ Logs rotate daily and retain 30 days
✅ No performance degradation (<10ms overhead for 50 symbols)
