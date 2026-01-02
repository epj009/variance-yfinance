# Tastytrade API Data Research Results

**Original Date:** December 26, 2025
**Updated:** December 30, 2025 (Verification Testing)
**Objective:** Explore using Tastytrade API to reduce legacy provider dependency
**Result:** **UPDATED** - OAuth credentials CAN access positions, but NOT streaming Greeks

## ⚠️ Update Notice (December 30, 2025)

**Live verification testing revealed that the original research findings were PARTIALLY INCORRECT.**

Key corrections:
- ✅ **Account endpoints ARE accessible** (original: timeout/no response)
- ✅ **Positions endpoint WORKS** (15 positions retrieved successfully)
- ❌ **DXLink streaming STILL blocked** (original finding confirmed)

**New verification script:** `scripts/verify_positions_greeks_access.py`

See updated findings below.

## Research Script

Created: `scripts/research_tastytrade_data.py`

Tests 5 different data endpoints to determine what we can access.

## Findings

### ✅ What Works (Currently Using)

**Endpoint:** `/market-metrics`

**Data Available:**
- Implied Volatility (IV)
- IV Rank & IV Percentile
- HV30 & HV90 (Historical Volatility)
- Liquidity ratings (0-5)
- Beta vs market
- SPY correlation (3-month)
- Earnings dates

**Authentication:** OAuth (client credentials + refresh token) ✅

---

### ❌ What Doesn't Work

#### 1. Real-Time Quote Data

**Endpoints Tested:**
- `/instruments/equities/{symbol}` → 404 Not Found
- `/symbols/{symbol}` → 404 Not Found
- `/quote/{symbol}` → 404 Not Found
- `/market-data/quotes/{symbol}` → 400 Bad Request
- `/option-chains/{symbol}/nested` → (varies)

**Result:** No price data accessible with OAuth-only credentials

**Needed For:**
- Current price (last, bid, ask, mark)
- Daily OHLC
- Real-time updates

---

#### 2. Historical Candles (OHLCV)

**Endpoints Tested:**
- `/market-data/candles/{symbol}` → 400 Bad Request
- `/instruments/candles/{symbol}` → 404 Not Found
- `/market-data/{symbol}/candles` → 400 Bad Request

**Result:** No historical price data accessible

**Needed For:**
- Historical volatility calculations (HV20, HV252)
- Backtesting
- Price charts

---

#### 3. DXLink/DXFeed Streaming

**Endpoints Tested:**
- `/dxlink-tokens` → Timeout
- `/quote-streamer-tokens` → 403 Forbidden
- `/sessions` → 403 Forbidden

**Result:** Streaming requires account-level access

**Error:** `403 Forbidden` indicates insufficient permissions

**Needed For:**
- Real-time price updates
- Live portfolio tracking
- Reduced API call volume

---

#### 4. Account Data ✅ **CORRECTED**

**Endpoints Tested:**
- `/customers/me` → ✅ **200 OK**
- `/customers/me/accounts` → ✅ **200 OK**
- `/accounts` → ❌ 403 Forbidden

**Result:** **OAuth credentials DO have account access**

**Verification (December 30, 2025):**
- Successfully retrieved account number: `5WZ12558`
- Successfully accessed account details
- Generic `/accounts` endpoint blocked, but customer-specific endpoints work

**Original Finding (December 26):** "Timeout / No Response"
**Correction:** Likely a temporary network/API issue. Subsequent testing confirms full account access.

---

#### 5. Position Data ✅ **NEW FINDING**

**Endpoint:** `/accounts/{account_number}/positions`

**Result:** ✅ **SUCCESS - Full position data accessible**

**Verification (December 30, 2025):**
- Retrieved **15 active positions** from live account
- Complete position details including:
  - Symbol, underlying symbol, instrument type
  - Quantity, direction (Long/Short)
  - Average open price, close price, cost basis
  - Multiplier, expiration dates
  - **Streamer symbols** (for subscribing to market data feeds)

**Sample Position Data:**
```json
{
  "account-number": "5WZ12558",
  "instrument-type": "Future Option",
  "symbol": "./ZNH6 OZNG6 260123P111",
  "underlying-symbol": "/ZNH6",
  "quantity": 1,
  "quantity-direction": "Short",
  "average-open-price": 0.125,
  "close-price": 0.046875,
  "cost-effect": "Debit",
  "multiplier": 1000,
  "streamer-symbol": "./OZNG26P111:XCBT"
}
```

**What This Enables:**
- Automated position sync (RFC-006 Phase 1)
- Eliminate CSV export workflow
- Real-time position updates
- Foundation for portfolio triage

**What's Missing:**
- Greeks (delta, gamma, theta, vega) - not included in position data
- Current market prices - requires separate quote endpoint
- P/L calculations - requires current prices + Greeks

---

## Why Price Data Isn't Available

### Authentication Levels **UPDATED**

Tastytrade API appears to have **tiered access**:

| Tier | Auth Method | Access | Status |
|------|-------------|---------|--------|
| **Market Data** | OAuth (client credentials) | Market metrics (IV, HV, liquidity) | ✅ **We have** |
| **Account Read** | OAuth (client credentials) | Accounts, positions, balances | ✅ **We have** |
| **Account Write** | OAuth (client credentials) | Orders, trades, account modifications | ❓ Unknown |
| **Streaming** | Premium subscription/entitlement | DXLink WebSocket (Greeks, real-time quotes) | ❌ **Blocked (403)** |

**Correction from original research:**
- OAuth credentials provide MORE access than initially thought
- Account-level READ endpoints (positions, balances) ARE accessible
- Streaming (Greeks) requires additional entitlement/subscription

**We have:** OAuth client credentials with account read access
**We're missing:** Premium streaming subscription for Greeks

### Account Session Authentication

**Different from OAuth:**
```python
# OAuth (what we use now)
POST /oauth/token
{
  "grant_type": "refresh_token",
  "client_id": "...",
  "client_secret": "...",
  "refresh_token": "..."
}

# Account session (needed for quotes)
POST /sessions
{
  "login": "username",
  "password": "password",
  "remember-me": true
}
# Returns: session-token for account-level endpoints
```

**Problem:** Using account credentials in automation requires:
1. Storing plaintext password (security risk)
2. Different authentication flow
3. Session management/renewal

---

## Conclusion **UPDATED**

### Current State (Corrected)

**Tastytrade provides via OAuth:**
- ✅ Volatility metrics (IV, HV30, HV90)
- ✅ Market quality data (liquidity, earnings)
- ✅ **Account positions** (symbol, quantity, cost basis) **[NEW]**
- ✅ **Position metadata** (expiration, strikes, multipliers) **[NEW]**
- ✅ **Streamer symbols** (for subscribing to data feeds) **[NEW]**
- ❌ Greeks (delta, gamma, theta, vega) - requires streaming subscription
- ❌ Real-time quotes - requires streaming subscription
- ❌ Price data (need separate endpoints or legacy provider)

**legacy provider provides:**
- ✅ Current prices
- ✅ Historical OHLCV
- ✅ Options chains
- ❌ **Rate limiting is the problem**

### Recommendations **REVISED**

#### ✅ NEW: Implement RFC-006 Phase 1 (Positions-Only Sync)

**NOW FEASIBLE** based on verified findings:

```bash
./variance --sync
```

**What it enables:**
1. Automated position sync from Tastytrade API
2. Eliminate 5-step CSV export workflow
3. Real-time position updates (quantities, cost basis, expirations)
4. Foundation for portfolio triage

**Implementation:**
- Call `/customers/me/accounts` → get account number
- Call `/accounts/{account}/positions` → get all positions
- Parse and normalize position data
- Save to `positions/live_tasty.json`
- PortfolioParser loads JSON (update to support JSON)

**What's missing:**
- Greeks (need for TOXIC THETA handler)
- Current prices (can fetch from legacy provider as fallback)

**Triage accuracy:** ~70-80% (all handlers except TOXIC THETA work)

**Effort:** ~4-6 hours implementation

---

#### ❌ NOT FEASIBLE: RFC-006 Phase 2 (Positions + Greeks)

**BLOCKED** - Cannot get Greeks via DXLink streaming:
- Streaming token endpoint returns 403 Forbidden
- OAuth scopes insufficient for streaming subscription
- Would require premium data subscription or different credentials

---

#### Continue: Improve legacy provider rate limit handling

For price data and Greeks (until streaming access obtained):

1. ✅ **Aggressive caching** (24-48 hour TTL)
2. ✅ **Request delays** (0.5-1s between symbols)
3. ✅ **Exponential backoff** (retry with increasing delays)
4. ✅ **Cache-first architecture** (only fetch when cache misses)
5. ✅ **Batch reduction** (fetch symbols sequentially, not in parallel)

---

## What We Already Do Well

**Current Tastytrade usage:**
- Market metrics for IV/HV/liquidity ✅
- Fallback to legacy provider for prices ✅
- Cache with 24h TTL ✅

**What needs improvement:**
- legacy provider rate limit handling
- Request throttling
- Better cache fallback logic

---

## Alternative Solutions

### Option 1: Paid Data Provider
- **Alpha Vantage** - $50/month, 75 API calls/min
- **Polygon.io** - $200/month, unlimited
- **IEX Cloud** - $9-199/month, tiered

**Pros:** Reliable, no rate limits
**Cons:** Adds cost, integration work

### Option 2: Local Database
- Download EOD data daily
- Store in SQLite/PostgreSQL
- Only fetch current day intraday

**Pros:** No rate limits, full control
**Cons:** Stale data, maintenance overhead

### Option 3: Better legacy provider Usage
- **Request throttling** (500ms delays)
- **IP rotation** (VPN/proxy)
- **Retry logic** (exponential backoff)
- **Cache everything** (48h TTL)

**Pros:** Free, works today
**Cons:** Still subject to Yahoo's limits

---

## Next Steps

1. ✅ Document research findings (this file)
2. ⬜ Implement better legacy provider rate limit handling:
   - Add request delays (0.5-1s between symbols)
   - Exponential backoff on 429 errors
   - Respect Retry-After headers
3. ⬜ Improve cache fallback:
   - Use stale cache when rate limited
   - Extend cache TTL to 48h
   - Add cache warming (pre-fetch during off-hours)
4. ⬜ Add request batching:
   - Process symbols sequentially
   - Add progress indicators
   - Respect rate limits

---

## Code References

**Research Script:** `scripts/research_tastytrade_data.py`

**Current Tastytrade Client:** `src/variance/tastytrade_client.py`
- Uses OAuth for /market-metrics only
- Already has context-aware IV scaling
- Returns HV30/HV90 from Tastytrade

**Market Data Service:** `src/variance/get_market_data.py`
- Line 751-904: TastytradeProvider (merges TT + legacy provider)
- Line 495-657: LegacyProvider (fallback)
- Line 18-91: market hours detection + holiday calendar

**Rate Limit Handling:** Currently minimal
- Line 555-577: Cache fallback added (Dec 26, 2025)
- No request throttling
- No exponential backoff
- No 429 detection/retry logic

---

## Testing Commands

### Original Research Script
```bash
# Run research script (original December 26 testing)
source .env.tastytrade
python3 scripts/research_tastytrade_data.py

# Test with custom symbols
python3 scripts/research_tastytrade_data.py --symbols SPY AAPL /ES

# Test streaming (will fail with 403)
python3 scripts/research_tastytrade_data.py --test-streaming

# JSON output
python3 scripts/research_tastytrade_data.py --json
```

### ✅ NEW: Verification Script (December 30, 2025)
```bash
# Verify positions and Greeks access (REST API only)
source .env.tastytrade
python3 scripts/verify_positions_greeks_access.py

# Test with tastytrade SDK (requires: pip install tastytrade)
source venv/bin/activate
python3 scripts/verify_positions_greeks_access.py --try-sdk

# Full verification (all tests including SDK + DXLinkStreamer)
source venv/bin/activate
python3 scripts/verify_positions_greeks_access.py --all
```

**Results from December 30 verification:**
- ✅ Accounts endpoint: **200 OK**
- ✅ Positions endpoint: **200 OK** (15 positions retrieved)
- ❌ DXLink streaming token: **403 Forbidden**

---

## Final Conclusion **UPDATED**

**Original conclusion (December 26):** "Stick with current architecture (Tastytrade for vol metrics, legacy provider for prices)."

**Updated conclusion (December 30):**
1. ✅ **Implement RFC-006 Phase 1** - Position sync is now feasible
2. ✅ **Keep Tastytrade for vol metrics** - Working as designed
3. ✅ **Keep legacy provider for prices** - Still needed for market data
4. ❌ **Greeks via streaming BLOCKED** - Requires premium subscription
5. ✅ **Improve legacy provider rate limits** - Still valuable optimization

**Next steps:**
1. Implement `--sync` command for automated position retrieval
2. Update PortfolioParser to support JSON input
3. Create broker bridge module (`src/variance/brokers/tastytrade_sync.py`)
4. Update RFC-006 status to "Phase 1 Feasible, Phase 2 Blocked"
