# Tastytrade API Data Research Results

**Date:** December 26, 2025
**Objective:** Explore using Tastytrade API to reduce yfinance dependency
**Result:** Limited - OAuth credentials insufficient for price/streaming data

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

#### 4. Account Data

**Endpoint:** `/customers/me/accounts`

**Result:** Timeout / No Response

**Indicates:** OAuth app credentials don't have account access

---

## Why Price Data Isn't Available

### Authentication Levels

Tastytrade API appears to have **tiered access**:

| Tier | Auth Method | Access |
|------|-------------|---------|
| **Public** | OAuth (client credentials) | Market metrics only |
| **Account** | Session token (username/password) | Quotes, positions, orders |
| **Premium** | Subscription/entitlement | DXLink streaming |

**We have:** OAuth client credentials (Tier 1)
**We need for prices:** Account-level session token (Tier 2)

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

## Conclusion

### Current State

**Tastytrade provides:**
- ✅ Volatility metrics (IV, HV30, HV90)
- ✅ Market quality data (liquidity, earnings)
- ❌ Price data (need account session)
- ❌ Streaming data (need premium entitlement)

**yfinance provides:**
- ✅ Current prices
- ✅ Historical OHLCV
- ✅ Options chains
- ❌ **Rate limiting is the problem**

### Recommendation

**Don't switch to Tastytrade for prices** because:

1. **Account credentials risky** - Storing password in plaintext
2. **Still incomplete** - Missing HV252, options chains, sector data
3. **Complexity increase** - Managing two auth systems
4. **Root problem unsolved** - yfinance rate limits are the real issue

**Instead, fix rate limiting:**

1. ✅ **Aggressive caching** (24-48 hour TTL)
2. ✅ **Request delays** (0.5-1s between symbols)
3. ✅ **Exponential backoff** (retry with increasing delays)
4. ✅ **Cache-first architecture** (only fetch when cache misses)
5. ✅ **Batch reduction** (fetch symbols sequentially, not in parallel)

---

## What We Already Do Well

**Current Tastytrade usage:**
- Market metrics for IV/HV/liquidity ✅
- Fallback to yfinance for prices ✅
- Cache with 24h TTL ✅

**What needs improvement:**
- yfinance rate limit handling
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

### Option 3: Better yfinance Usage
- **Request throttling** (500ms delays)
- **IP rotation** (VPN/proxy)
- **Retry logic** (exponential backoff)
- **Cache everything** (48h TTL)

**Pros:** Free, works today
**Cons:** Still subject to Yahoo's limits

---

## Next Steps

1. ✅ Document research findings (this file)
2. ⬜ Implement better yfinance rate limit handling:
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
- Line 751-904: TastytradeProvider (merges TT + yfinance)
- Line 495-657: YFinanceProvider (fallback)
- Line 18-91: market hours detection + holiday calendar

**Rate Limit Handling:** Currently minimal
- Line 555-577: Cache fallback added (Dec 26, 2025)
- No request throttling
- No exponential backoff
- No 429 detection/retry logic

---

## Testing Commands

```bash
# Run research script
source .env.tastytrade
python3 scripts/research_tastytrade_data.py

# Test with custom symbols
python3 scripts/research_tastytrade_data.py --symbols SPY AAPL /ES

# Test streaming (will fail with 403)
python3 scripts/research_tastytrade_data.py --test-streaming

# JSON output
python3 scripts/research_tastytrade_data.py --json
```

---

**Conclusion:** Stick with current architecture (Tastytrade for vol metrics, yfinance for prices). Focus effort on **better rate limit handling** rather than switching data providers.
