# ATM Options Quotes Implementation Plan

## Problem Statement

**Current Issue:** Yield filter fails for all symbols with "no option pricing available"

**Root Cause:** We fetch IV/HV/prices from Tastytrade but NOT options quotes (ATM call/put bid/ask)

**Impact:** Cannot calculate yield = (Straddle Mid / BPR) * (30/45) * 100%

---

## Three API Approaches

### Option 1: Direct REST - `/market-data/by-type` Only

**Endpoint:** `GET /market-data/by-type?equity-option[]={OCC_SYMBOL}`

**Flow:**
1. Get underlying price from existing call
2. Calculate ATM strike (round to nearest)
3. Hardcode 45 DTE expiration (or use current month + 1.5 months)
4. Construct OCC symbols manually
5. Fetch quotes

**Pros:**
- ✅ Simplest - one API call
- ✅ No chain parsing needed
- ✅ Fast batch support (100 symbols)

**Cons:**
- ❌ **CRITICAL:** Must construct OCC symbols WITHOUT knowing actual available strikes/expirations
- ❌ Risk of requesting non-existent options
- ❌ Hardcoded DTE may not match actual expirations
- ❌ ATM strike rounding may miss actual strike

**Verdict:** ❌ **NOT RECOMMENDED** - Too many assumptions, high failure rate

---

### Option 2: DXLink WebSocket `Quote` Events

**Connection:** `wss://tasty-openapi-ws.dxfeed.com/realtime`

**Flow:**
1. Get option chain to find ATM strikes/expirations
2. Construct DXLink option symbols
3. Subscribe to Quote events
4. Wait for real-time quotes
5. Extract bid/ask

**Pros:**
- ✅ Real-time streaming
- ✅ Most accurate data
- ✅ Already have DXLink infrastructure
- ✅ No rate limits

**Cons:**
- ❌ Async/event-driven complexity
- ❌ Overkill for batch screening (not continuous monitoring)
- ❌ Need to manage WebSocket lifecycle per screening run
- ❌ Still requires chain call first
- ❌ Harder to debug/maintain

**Verdict:** ⚠️ **USE LATER** - Save for real-time position monitoring, not screening

---

### Option 3: Hybrid - Option Chain + REST Quotes ⭐ RECOMMENDED

**Endpoints:**
- `GET /option-chains/{symbol}/compact` - Get strikes/expirations
- `GET /market-data/by-type` - Get quotes for constructed OCC symbols

**Flow:**
1. Batch fetch compact chains for all symbols
2. Parse each chain to find:
   - ATM strike (closest to underlying price)
   - Nearest 45 DTE expiration
3. Construct OCC symbols for ATM call + put
4. Batch fetch all option quotes
5. Merge bid/ask into market data

**Pros:**
- ✅ **BEST:** No guessing - uses actual available strikes/expirations
- ✅ REST-only (synchronous, simple)
- ✅ Compact endpoint = minimal payload
- ✅ Batch support for chains AND quotes
- ✅ Easy to debug
- ✅ $0 cost, no rate limits

**Cons:**
- ❌ Two API calls instead of one
- ❌ Need chain parser

**Performance:**
- 50 symbols: ~200ms total (100ms chain + 100ms quotes)
- Acceptable overhead for screening

**Verdict:** ✅ **RECOMMENDED** - Best balance of accuracy, simplicity, and performance

---

## Implementation Details - Option 3 (Hybrid)

### Important: Futures Options ✅ RESEARCHED

**See:** `docs/research/tastytrade-futures-options-research.md` for complete details.

**Key Differences from Equity Options:**

| Feature | Equity | Futures |
|---------|--------|---------|
| Chain Endpoint | `/option-chains/{symbol}/compact` | `/futures-option-chains/{symbol}` |
| Compact Available | ✅ Yes | ❌ **NO - Full chain only** |
| Symbol Format | `AAPL  260220C00170000` | `./ESH6 E2CF6 260114P5990` |
| Quote Param | `equity-option[]` | `future-option[]` |
| Chain Size | ~200 options | ~18,000 options (/ES) |

**Challenges:**
1. ❌ No compact endpoint - must fetch FULL chain (10-20K options)
2. Different symbol format: `./UNDERLYING ROOT EXPDATE{TYPE}{STRIKE}`
3. Requires client-side filtering for DTE and ATM strikes
4. Large response size (~5-10MB for /ES)

**Implementation Phases:**
- **Phase 1 (MVP):** Equity options only
  - Use `/option-chains/{symbol}/compact` - fast, small response
  - OCC format well-documented
  - Covers 80% of use cases (most screening on equities)

- **Phase 2 (Future):** Add futures options
  - Implement full chain parsing with filtering
  - Cache chains (15 min TTL - expirations don't change often)
  - Consider DXLink streaming if performance is issue

**For MVP:** ✅ **Implement equities first**, futures options can wait or gracefully degrade.

---

### Step 1: Add Option Chain Methods to `tastytrade_client.py`

```python
def get_option_chains_compact(self, symbols: list[str]) -> dict[str, dict]:
    """
    Fetch compact option chains for multiple symbols.

    Args:
        symbols: List of underlying symbols (e.g., ['AAPL', 'SPY', '/ES'])

    Returns:
        Dictionary mapping symbol to compact chain data

    Example Response:
        {
            "AAPL": {
                "expirations": [
                    {
                        "expiration-date": "2026-02-20",
                        "days-to-expiration": 50,
                        "strikes": [150.0, 155.0, 160.0, ...]
                    },
                    ...
                ]
            }
        }
    """
    # For equities: GET /option-chains/{symbol}/compact
    # For futures: GET /futures-option-chains/{symbol}/compact
    pass

def find_atm_options(
    self,
    symbol: str,
    chain: dict,
    underlying_price: float,
    target_dte: int = 45
) -> tuple[str, str]:
    """
    Find ATM call and put OCC symbols from chain.

    Args:
        symbol: Underlying symbol
        chain: Compact chain data from get_option_chains_compact()
        underlying_price: Current underlying price
        target_dte: Target days to expiration (default: 45)

    Returns:
        (call_occ_symbol, put_occ_symbol)

    Example:
        ("AAPL  260220C00170000", "AAPL  260220P00170000")
    """
    # 1. Find expiration closest to target_dte
    # 2. Find strike closest to underlying_price
    # 3. Construct OCC symbols
    pass

def get_option_quotes(self, occ_symbols: list[str]) -> dict[str, dict]:
    """
    Fetch quotes for specific option symbols.

    Uses /market-data/by-type with equity-option[] or future-option[] params.

    Args:
        occ_symbols: List of OCC option symbols

    Returns:
        Dictionary mapping OCC symbol to quote data (bid, ask, mid, mark, etc.)
    """
    # Determine if equity or futures options
    # Call /market-data/by-type with appropriate param
    pass
```

### Step 2: Update `pure_tastytrade_provider.py`

Add option quote fetching to `get_market_data()`:

```python
def get_market_data(self, symbols: list[str], *, include_returns: bool = False):
    # ... existing code ...

    # NEW: Step 2.5: Fetch option chains and quotes
    option_quotes = {}
    if self.tt_client:
        # Get compact chains
        chains = self.tt_client.get_option_chains_compact(unique_symbols)

        # Find ATM options for each symbol
        atm_symbols = []
        atm_map = {}  # Map underlying -> (call_symbol, put_symbol)

        for symbol in unique_symbols:
            if symbol in chains:
                price = tt_prices.get(symbol, {}).get("price")
                if price:
                    call_occ, put_occ = self.tt_client.find_atm_options(
                        symbol, chains[symbol], price, target_dte=45
                    )
                    atm_symbols.extend([call_occ, put_occ])
                    atm_map[symbol] = (call_occ, put_occ)

        # Batch fetch option quotes
        if atm_symbols:
            option_quotes = self.tt_client.get_option_quotes(atm_symbols)

    # ... merge option quotes into results ...
```

### Step 3: Update `_merge_tastytrade_data()`

Add ATM bid/ask fields:

```python
def _merge_tastytrade_data(..., option_quotes: dict = None):
    # ... existing code ...

    # Add option quotes if available
    if option_quotes and symbol in atm_map:
        call_occ, put_occ = atm_map[symbol]
        call_quote = option_quotes.get(call_occ)
        put_quote = option_quotes.get(put_occ)

        if call_quote and put_quote:
            merged["call_bid"] = call_quote.get("bid")
            merged["call_ask"] = call_quote.get("ask")
            merged["put_bid"] = put_quote.get("bid")
            merged["put_ask"] = put_quote.get("ask")

            # Also set ATM totals for backward compat
            merged["atm_bid"] = (call_quote.get("bid", 0) or 0) + (put_quote.get("bid", 0) or 0)
            merged["atm_ask"] = (call_quote.get("ask", 0) or 0) + (put_quote.get("ask", 0) or 0)
```

### Step 4: OCC Symbol Construction

**Format:** `SYMBOL  YYMMDDCTTTTTTKKKK`
- `SYMBOL` - 6 chars, left-aligned, space-padded
- `YYMMDD` - Expiration date
- `C` - Call/Put (C or P)
- `TTTTTT` - Strike * 1000, 8 digits total

**Examples:**
- `AAPL  260220C00170000` - AAPL Feb 20, 2026 $170 Call
- `SPY   260115P00450000` - SPY Jan 15, 2026 $450 Put

**Futures Options:** ✅ **RESEARCHED** (see `docs/research/tastytrade-futures-options-research.md`)
- Format: `./UNDERLYING ROOT EXPDATE{TYPE}{STRIKE}` (e.g., `./ESH6 E2CF6 260114P5990`)
- Use `/futures-option-chains/{symbol}` endpoint (no `/compact` available)
- Use `future-option[]` param in `/market-data/by-type`
- ⚠️ **Phase 2 feature** - Implement equities first
- Requires full chain parsing (18K+ options for /ES)
- Recommend separate implementation with caching

### Step 5: Handle Edge Cases

**Missing Chains:**
- If chain unavailable, skip option quotes
- Yield filter will correctly report "no option pricing available"
- Don't crash

**No 45 DTE Expiration:**
- Use closest available (30-60 DTE range)
- Document in comments

**Wide Bid-Ask Spreads:**
- Accept as-is (market reality)
- Yield calculation uses mid = (bid + ask) / 2

**Futures vs Equities:**
- Detect with `symbol.startswith("/")`
- Use `/futures-option-chains/` for futures
- Use `/option-chains/` for equities

---

## Testing Plan

### Phase 1: Unit Tests

```python
def test_find_atm_strike():
    """Test ATM strike selection from chain."""
    chain = {
        "expirations": [{
            "strikes": [150.0, 155.0, 160.0, 165.0, 170.0]
        }]
    }
    # Price = 162.5 -> should select 160 or 165 (closest)
    assert find_atm_strike(chain, 162.5) in [160.0, 165.0]

def test_occ_symbol_construction():
    """Test OCC symbol formatting."""
    symbol = build_occ_symbol("AAPL", "2026-02-20", 170.0, "C")
    assert symbol == "AAPL  260220C00170000"
```

### Phase 2: Integration Test

```bash
# Test with real Tastytrade API
source .venv/bin/activate
source .env.tastytrade

python -c "
from variance.tastytrade_client import TastytradeClient

client = TastytradeClient()

# Test chain fetch
chains = client.get_option_chains_compact(['AAPL'])
print('Chain expirations:', chains['AAPL']['expirations'][:3])

# Test ATM finder
call, put = client.find_atm_options('AAPL', chains['AAPL'], 170.0)
print(f'ATM Call: {call}')
print(f'ATM Put: {put}')

# Test quote fetch
quotes = client.get_option_quotes([call, put])
print(f'Call bid/ask: {quotes[call][\"bid\"]}/{quotes[call][\"ask\"]}')
print(f'Put bid/ask: {quotes[put][\"bid\"]}/{quotes[put][\"ask\"]}')
"
```

### Phase 3: End-to-End Screening Test

```bash
# Run screener with new option quotes
./screen 10 --debug

# Verify:
# - No "no option pricing available" errors
# - Yield values calculated correctly
# - Candidates pass/fail based on actual yield
```

---

## Rollout Plan

1. **Implement in tastytrade_client.py** (~3 hours)
   - `get_option_chains_compact()`
   - `find_atm_options()`
   - `get_option_quotes()`

2. **Update pure_tastytrade_provider.py** (~2 hours)
   - Integrate chain fetching
   - Add option quote merging
   - Update `_merge_tastytrade_data()`

3. **Test & Debug** (~2 hours)
   - Unit tests
   - Integration tests
   - Fix edge cases

4. **Documentation** (~1 hour)
   - Update ADR if needed
   - Document new fields
   - Update API call inventory

**Total Effort:** ~8 hours (1 day)

---

## API Call Inventory (After Implementation)

**Per Screening Run (50 symbols):**
1. `/market-metrics` (batch) - IV/IVR/IVP/liquidity - **existing**
2. `/market-data/by-type` (batch) - Underlying prices - **existing**
3. **NEW:** `/option-chains/{symbol}/compact` (per-symbol or batched?) - Strikes/expirations
4. **NEW:** `/market-data/by-type` (batch) - Option quotes

**Total:** 3-4 API calls for complete market data

**Performance:** ~300-400ms for 50 symbols (acceptable)

---

## Alternative: Lazy Loading

If API overhead is too high, implement lazy loading:

```python
def get_market_data(symbols, fetch_options=False):
    """
    Args:
        fetch_options: If True, include ATM option quotes (adds 100-200ms)
    """
```

Then enable only when yield filter is active:

```python
# In screening pipeline
needs_yield = config.min_yield_percent > 0
market_data = provider.get_market_data(symbols, fetch_options=needs_yield)
```

---

## Success Criteria

✅ Yield filter works for equities
✅ Yield filter works for futures (if futures options available)
✅ No "no option pricing available" for symbols with active options
✅ Graceful degradation if options unavailable
✅ <500ms overhead for 50 symbols
✅ All existing tests pass
