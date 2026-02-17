# Tastytrade Futures Options Research

## API Endpoints

### 1. Futures Option Chains

**Endpoint:** `GET /futures-option-chains/{symbol}`

**Example:** `GET /futures-option-chains//ES`

**Important:**
- ❌ **NO `/compact` endpoint** - Only full chain available
- ✅ Returns all strikes and expirations (18,000+ options for /ES!)
- Must filter client-side for desired DTE and strikes

**Response Structure:**
```json
{
  "data": {
    "items": [
      {
        "symbol": "./ESH6 E2CF6 260114P5990",
        "exchange-symbol": "E2CF6 P5990",
        "streamer-symbol": "./E2CF26P5990:XCME",
        "option-root-symbol": "E2CF",
        "option-type": "P",
        "strike-price": "5990.0",
        "expiration-date": "2026-01-14",
        "days-to-expiration": 13,
        "underlying-symbol": "/ESH6",
        "root-symbol": "/ES",
        "exercise-style": "American",
        ...
      }
    ]
  }
}
```

### 2. Futures Option Quotes

**Endpoint:** `GET /market-data/by-type?future-option[]={symbol}`

**Example:** `GET /market-data/by-type?future-option[]=./ESH6 E2CF6 260114P5990`

**Response:**
```json
{
  "data": {
    "items": [
      {
        "symbol": "./ESH6 E2CF6 260114P5990",
        "instrument-type": "Future Option",
        "bid": "0.95",
        "ask": "1.25",
        "mid": "1.1",
        "mark": "1.1",
        "delta": "-0.024965634",
        "gamma": "0.000116811",
        "theta": "-1.062202582",
        "vega": "0.783499278",
        "theo-price": "4.831539235",
        "open-interest": 0
      }
    ]
  }
}
```

---

## Symbol Format Breakdown

**Format:** `./UNDERLYING ROOT EXPDATE{TYPE}{STRIKE}`

**Examples:**
- `./ESH6 E2CF6 260114P5990` - /ES March 2026, E2CF root, Jan 14 Put @ 5990
- `./ESH6 E2CF6 260114C5990` - Same but Call
- `./ESH6 E3DF6 260115C5990` - /ES March 2026, E3DF root, Jan 15 Call @ 5990

**Components:**
- `./ESH6` - Underlying futures contract (/ES March 2026)
- `E2CF6` - Option root symbol (weekly/monthly identifier)
- `260114` - Expiration date (YYMMDD format)
- `P` or `C` - Put or Call
- `5990` - Strike price (integer, no decimals for /ES)

**DXLink Streamer Symbol:**
- Format: `./E2CF26P5990:XCME`
- Used for WebSocket subscriptions

---

## Comparison to Equity Options

| Feature | Equity Options | Futures Options |
|---------|----------------|-----------------|
| **Chain Endpoint** | `/option-chains/{symbol}` | `/futures-option-chains/{symbol}` |
| **Compact Format** | ✅ `/option-chains/{symbol}/compact` | ❌ Not available |
| **Symbol Format** | OCC: `AAPL  260220C00170000` | Custom: `./ESH6 E2CF6 260114P5990` |
| **Strike Format** | Padded 8 digits: `00170000` = $170.00 | Integer: `5990` = 5990 |
| **Quote Param** | `equity-option[]` | `future-option[]` |
| **Typical Chain Size** | 100-500 options | 10,000-20,000 options |

---

## Implementation Considerations

### Challenge: No Compact Endpoint

**Problem:** Full chain returns 18,000+ options for /ES
**Impact:** Large response, slow parsing

**Solution:** Client-side filtering
```python
def filter_futures_options(chain_items, target_dte=45, underlying_price=6000):
    """Filter futures option chain to relevant options."""
    # 1. Filter by DTE range (30-60 days)
    near_term = [
        item for item in chain_items
        if 30 <= item['days-to-expiration'] <= 60
    ]

    # 2. Filter by ATM strikes (within 5% of underlying)
    tolerance = underlying_price * 0.05
    atm_strikes = [
        item for item in near_term
        if abs(float(item['strike-price']) - underlying_price) < tolerance
    ]

    return atm_strikes
```

### Finding ATM Strike

```python
def find_futures_atm_options(chain_items, underlying_price, target_dte=45):
    """
    Find ATM call and put for futures options.

    Returns:
        (call_symbol, put_symbol) or (None, None)
    """
    # Filter to near-term
    near_term = [
        item for item in chain_items
        if abs(item['days-to-expiration'] - target_dte) < 15
    ]

    if not near_term:
        return None, None

    # Group by expiration
    from collections import defaultdict
    by_exp = defaultdict(list)
    for item in near_term:
        by_exp[item['expiration-date']].append(item)

    # Find closest expiration to target DTE
    target_exp = min(
        by_exp.keys(),
        key=lambda exp: abs(by_exp[exp][0]['days-to-expiration'] - target_dte)
    )

    # Find ATM strike
    strikes = by_exp[target_exp]
    atm_strike = min(
        strikes,
        key=lambda x: abs(float(x['strike-price']) - underlying_price)
    )['strike-price']

    # Get call and put at that strike
    call = next(
        (item for item in strikes
         if item['strike-price'] == atm_strike and item['option-type'] == 'C'),
        None
    )
    put = next(
        (item for item in strikes
         if item['strike-price'] == atm_strike and item['option-type'] == 'P'),
        None
    )

    return (call['symbol'] if call else None, put['symbol'] if put else None)
```

---

## Performance Impact

**Full Chain Fetch:**
- Response size: ~5-10MB for /ES
- Parse time: ~500ms (18,000 items)
- Network: ~200ms

**Optimization:**
- Cache chains for 15 minutes (expirations don't change often)
- Pre-filter on server if possible (future API enhancement request?)

**Alternative:** Use DXLink for futures option quotes if performance is critical

---

## Test Examples

### /ES (E-mini S&P 500)
```
./ESH6 E2CF6 260114P5990  - March 2026 contract, Jan 14 Put @ 5990
./ESH6 E2CF6 260114C5990  - March 2026 contract, Jan 14 Call @ 5990
```

### /CL (Crude Oil)
```
./CLG6 LOF6 260110C7500  - Feb 2026 contract, Jan 10 Call @ $75.00
./CLG6 LOF6 260110P7500  - Feb 2026 contract, Jan 10 Put @ $75.00
```

### /NG (Natural Gas)
```
./NGF6 ON6 260110C3000  - Jan 2026 contract, Jan 10 Call @ $3.00
./NGF6 ON6 260110P3000  - Jan 2026 contract, Jan 10 Put @ $3.00
```

---

## Key Differences from Plan

**Original Assumption (WRONG):**
- Futures options use compact endpoint
- Symbol format similar to OCC

**Actual Reality:**
- ❌ No compact endpoint
- ❌ Completely different symbol format
- ✅ BUT quotes work via `/market-data/by-type` with `future-option[]` param
- ✅ Response includes bid/ask/Greeks just like equity options

**Updated Recommendation:**
- Implement equity options first (simpler, compact endpoint)
- Add futures options as separate feature (requires full chain parsing)
- Consider caching futures chains (changes infrequently)
