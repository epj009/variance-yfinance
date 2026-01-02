# Tastytrade Options Quote Endpoints - Comparison

## Option 1: REST API `/market-data/by-type` with option symbols

**Endpoint:** `GET /market-data/by-type`

**Parameters:**
- `equity-option[]` - Equity option OCC symbols (e.g., SPY 220617P00150000)
- `future-option[]` - Future option symbols

**Pros:**
- ✅ Simple REST call (no WebSocket complexity)
- ✅ Batch support (100 symbols combined)
- ✅ Same endpoint we already use for underlying prices
- ✅ Returns bid, ask, bidSize, askSize, mid, mark, last
- ✅ Synchronous - easy to integrate

**Cons:**
- ❌ Need to construct OCC option symbols first
- ❌ Need to know which strikes/expirations to request
- ❌ Snapshot data (not real-time stream)
- ❌ Extra API call per screening run

**Data Flow:**
1. Get underlying price
2. Calculate ATM strike
3. Find nearest 45 DTE expiration from `/option-chains/{symbol}`
4. Construct OCC symbols (ATM call + put)
5. Fetch quotes via `/market-data/by-type`

---

## Option 2: DXLink WebSocket `Quote` Events

**Connection:** `wss://tasty-openapi-ws.dxfeed.com/realtime`

**Event Type:** `Quote`

**Pros:**
- ✅ Real-time streaming (live bid/ask updates)
- ✅ No rate limits
- ✅ Already have DXLink infrastructure
- ✅ Can subscribe to multiple options simultaneously
- ✅ Most accurate/fresh data

**Cons:**
- ❌ Requires WebSocket connection management
- ❌ Async/event-driven (harder to integrate)
- ❌ Still need option chain to find strikes
- ❌ Overhead for one-time screening (not continuous monitoring)
- ❌ Overkill for batch screening use case

**Data Flow:**
1. Get underlying price
2. Find ATM strike from `/option-chains/{symbol}`
3. Construct DXLink symbols
4. Subscribe to Quote events
5. Wait for quotes to arrive
6. Extract bid/ask

---

## Option 3: Hybrid - Option Chain + REST Quotes

**Endpoints:** 
- `GET /option-chains/{symbol}/compact` (get strikes/expirations)
- `GET /market-data/by-type` (get quotes for specific options)

**Pros:**
- ✅ Best of both worlds
- ✅ Compact endpoint returns minimal data (fast)
- ✅ Can filter to ATM strikes only
- ✅ Single batch call for quotes
- ✅ No WebSocket complexity

**Cons:**
- ❌ Two API calls per symbol
- ❌ Need to parse option chain response

**Data Flow:**
1. Fetch `/option-chains/{symbol}/compact` for all symbols
2. For each symbol:
   - Parse chain to find ATM strike
   - Find nearest 45 DTE expiration
   - Build OCC symbols
3. Batch fetch all option quotes via `/market-data/by-type`

---

## RECOMMENDATION

**Use Option 3: Hybrid Approach**

**Reasoning:**
1. **Simplicity:** REST-only, no WebSocket complexity
2. **Efficiency:** Compact chains are small, batch quotes
3. **Accuracy:** Real-time REST data is sufficient for screening
4. **Maintainability:** Easy to debug and test
5. **Cost:** $0, no rate limits

**Implementation:**
```python
# Step 1: Get option chains (batched)
chains = tastytrade_client.get_option_chains_compact(['AAPL', 'SPY', '/ES'])

# Step 2: Find ATM options for each symbol
atm_options = []
for symbol, chain in chains.items():
    underlying_price = get_price(symbol)
    atm_strike = find_atm_strike(chain, underlying_price)
    dte_45_exp = find_nearest_expiration(chain, target_dte=45)
    
    atm_call = build_occ_symbol(symbol, dte_45_exp, atm_strike, 'C')
    atm_put = build_occ_symbol(symbol, dte_45_exp, atm_strike, 'P')
    
    atm_options.extend([atm_call, atm_put])

# Step 3: Batch fetch option quotes
quotes = tastytrade_client.get_market_data(atm_options)

# Step 4: Extract ATM bid/ask for yield calculation
for symbol in symbols:
    call_quote = quotes[atm_call]
    put_quote = quotes[atm_put]
    
    atm_bid = call_quote['bid'] + put_quote['bid']
    atm_ask = call_quote['ask'] + put_quote['ask']
```

**Performance:**
- For 50 symbols: 1 chain call + 1 quote call = ~2 API calls
- Chain call: ~100ms
- Quote call: ~100ms
- Total: ~200ms for all 50 symbols

