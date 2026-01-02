# PARKED: Broker Position Sync Implementation

**Status:** PARKED - Tabled for later
**Date Parked:** December 31, 2025
**Reason:** User wants to "trim the fat" and clean up codebase before adding this complexity

---

## Context

User wants to sync broker positions (from Tastytrade) into Variance for portfolio-aware screening.

**User Quote:** "lets table this for later, somehow. I'm working on cleaning up and organizing the codebase overall and dont want to introduce this complexity until i feel like we have trimmed all the fat."

---

## What Was Decided

### Architecture: Producer-Consumer Pattern

**Producer:** Separate script fetches positions from Tastytrade API
**Consumer:** Variance reads from cache (SQLite `.market_cache.db`)

**Why Not JSON:** User already uses SQLite for market data caching - reuse existing infrastructure

### Storage Schema

```sql
CREATE TABLE broker_positions (
    symbol TEXT PRIMARY KEY,
    account_number TEXT,
    quantity REAL,
    average_price REAL,
    current_price REAL,
    unrealized_pnl REAL,
    position_type TEXT,  -- 'stock', 'option', etc.
    last_updated TIMESTAMP,
    data_source TEXT DEFAULT 'tastytrade'
);
```

### Implementation Files

**Producer Script:** `scripts/sync_broker_positions.py`
- Fetches positions from Tastytrade API
- Writes to SQLite cache
- Run via cron or manually

**Consumer Integration:** `src/variance/screening/enrichment/broker.py`
- Reads from SQLite cache
- Enriches candidates with `is_held` flag
- Used in Vote logic (BUY → HOLD/SCALE)

---

## Tastytrade API Research

### Positions ARE Accessible

From `docs/implementation/tastytrade-data-research.md`:

> **CORRECTION (Dec 30, 2025):** Positions ARE accessible via `/accounts/{account-number}/positions`
>
> Previous documentation incorrectly stated they were not available. The CLI tool limitation does not reflect API capabilities.

**Endpoint:** `GET /accounts/{account-number}/positions`

**Returns:**
```json
{
  "items": [
    {
      "symbol": "AAPL",
      "quantity": "100",
      "average-open-price": "150.25",
      "mark": "155.50",
      "unrealized-profit-loss": "525.00"
    }
  ]
}
```

---

## User Configuration

**Question:** Where do users store broker credentials?

**Answer:** Same `.env` pattern as Tastytrade market data:

```bash
# .env
TASTYTRADE_USERNAME=user@example.com
TASTYTRADE_PASSWORD=yourpassword
TASTYTRADE_ACCOUNT_NUMBER=5YZ12345
```

**Documentation Location:** `docs/user-guide/broker-sync-setup.md` (to be created)

---

## Next Steps (When Resuming)

1. Create `scripts/sync_broker_positions.py` producer script
2. Add broker_positions table to SQLite schema
3. Create `src/variance/screening/enrichment/broker.py` enrichment step
4. Update Vote logic to use `is_held` flag
5. Document setup in user guide
6. Add cron example for automated sync

---

## Files Referenced

- `docs/implementation/tastytrade-data-research.md` - API capabilities research
- `.market_cache.db` - Existing SQLite cache (reuse for positions)
- `src/variance/tastytrade_client.py` - Existing Tastytrade auth (reuse)

---

**Ready to implement when user signals to resume.**
