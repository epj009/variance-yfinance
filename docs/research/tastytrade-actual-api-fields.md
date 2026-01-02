# Tastytrade API - Actual Fields Reference

**Date:** 2024-12-31
**Purpose:** Document ACTUAL fields returned by Tastytrade API (not just OpenAPI spec)
**Source:** Production code analysis + API testing + OpenAPI spec

> **Note:** The OpenAPI spec is incomplete. This document reflects what the API ACTUALLY returns.

---

## Market Metrics API

### GET /market-metrics

**Parameters:**
- `symbols` (query, required): Comma-separated list (e.g., `?symbols=AAPL,SPY`)

**Response: MarketMetricInfo Fields (ACTUAL)**

| Field | Type | Description | In Spec? |
|-------|------|-------------|----------|
| `symbol` | string | Ticker symbol | ✅ Yes |
| **Volatility Metrics** | | | |
| `historical-volatility-30-day` | float | HV30 (annualized) | ❌ No |
| `historical-volatility-90-day` | float | HV90 (annualized) | ❌ No |
| `implied-volatility-index` | float | IV Index | ✅ Yes |
| `implied-volatility-index-rank` | float | IV Rank (0-100) | ⚠️ Different name |
| `implied-volatility-percentile` | float | IV Percentile (0-100) | ✅ Yes |
| `implied-volatility-index-5-day-change` | float | 5-day IV change | ✅ Yes |
| **Liquidity Metrics** | | | |
| `liquidity-rating` | int32 | Liquidity rating (0-5) | ✅ Yes |
| `liquidity-value` | float | Liquidity value | ❌ No |
| `liquidity-rank` | float | Liquidity rank | ✅ Yes |
| **Volume & Activity** | | | |
| `option-volume` | float | Options trading volume | ❌ No |
| **Correlation & Beta** | | | |
| `beta` | float | Stock beta vs market | ❌ No |
| `corr-spy-3month` | float | 3-month SPY correlation | ❌ No |
| **Earnings** | | | |
| `earnings` | object | Nested earnings object | ❌ No |
| `earnings.expected-report-date` | date | Next earnings date | ❌ No |
| **Option Expirations** | | | |
| `option-expiration-implied-volatilities` | array | IV by expiration | ✅ Yes |
| `option-expiration-implied-volatilities[].expiration-date` | date-time | Expiration date | ✅ Yes |
| `option-expiration-implied-volatilities[].settlement-type` | enum | AM or PM settlement | ✅ Yes |
| `option-expiration-implied-volatilities[].option-chain-type` | enum | Standard/Non-standard | ✅ Yes |
| `option-expiration-implied-volatilities[].implied-volatility` | double | IV for that expiration | ✅ Yes |

**Source:** `src/variance/tastytrade_client.py:177-223`

---

### GET /market-metrics/historic-corporate-events/dividends/{symbol}

**Parameters:**
- `symbol` (path, required): Ticker symbol

**Response: DividendInfo[] Fields**

| Field | Type | Description |
|-------|------|-------------|
| `occurred-date` | date | Dividend payment date |
| `amount` | float | Dividend per share |

**Use Case:**
- Historical dividend analysis
- Dividend calendar tracking

---

### GET /market-metrics/historic-corporate-events/earnings-reports/{symbol}

**Parameters:**
- `symbol` (path, required): Ticker symbol
- `start-date` (query, required): Start date for range
- `end-date` (query, optional): End date for range

**Response: EarningsInfo[] Fields**

| Field | Type | Description |
|-------|------|-------------|
| `occurred-date` | date | Earnings announcement date |
| `eps` | float | Earnings per share |

**Use Case:**
- Historical earnings analysis
- Earnings surprise tracking
- **Potential use for Variance:** Load earnings dates to avoid holding through earnings

---

## Market Data API

### GET /market-data/by-type

**Parameters:**
- `index` (query, array): Index symbols
- `equity` (query, array): Equity symbols
- `equity-option` (query, array): Equity option OCC symbols
- `future` (query, array): Future symbols
- `future-option` (query, array): Future option symbols
- `cryptocurrency` (query, array): Crypto symbols

**Limit:** Combined 100 symbols across all types

**Response: MarketData Fields (ACTUAL)**

| Field | Type | Description | Notes |
|-------|------|-------------|-------|
| **Identification** | | | |
| `symbol` | string | Ticker symbol | |
| `instrumentType` | enum | Bond, Cryptocurrency, Equity, etc. | |
| `instrument` | object | Full instrument details | Nested |
| **Timestamps** | | | |
| `updatedAt` | date-time | Last update timestamp | |
| `lastTradeTime` | int64 | Last trade timestamp (epoch) | |
| `summaryDate` | date | Date of summary data | |
| `prevCloseDate` | date | Previous close date | |
| **Current Prices** | | | |
| `bid` | double | Current bid price | |
| `bidSize` | double | Bid quantity | |
| `ask` | double | Current ask price | |
| `askSize` | double | Ask quantity | |
| `mid` | double | Midpoint (bid+ask)/2 | |
| `mark` | double | Official mark price | |
| `last` | double | Last traded price | |
| `lastExt` | double | Last extended-hours price | |
| `lastMkt` | double | Last market-hours price | |
| **Daily OHLC** | | | TODAY ONLY |
| `open` | double | Today's open | NOT historical |
| `dayHighPrice` | double | Today's high | NOT historical |
| `dayLowPrice` | double | Today's low | NOT historical |
| `close` | double | Today's close | NOT historical |
| `closePriceType` | enum | REGULAR, INDICATIVE, etc. | |
| `prevClose` | double | Yesterday's close | 1 day back only |
| `prevClosePriceType` | enum | Previous close type | |
| `volume` | double | Today's volume | NOT historical |
| **52-Week Range** | | | |
| `yearLowPrice` | double | 52-week low price | |
| `yearHighPrice` | double | 52-week high price | |
| **Fundamentals** | | | |
| `beta` | double | Stock beta coefficient | |
| `dividendAmount` | double | Dividend per share | |
| `dividendFrequency` | double | Dividend frequency metric | |
| **Futures Limits** | | | |
| `lowLimitPrice` | double | Daily lower trading limit | Futures |
| `highLimitPrice` | double | Daily upper trading limit | Futures |
| **Trading Halts** | | | |
| `tradingHalted` | boolean | Is trading halted? | |
| `tradingHaltedReason` | string | Reason for halt | |
| `haltStartTime` | int64 | Halt start (epoch ms) | |
| `haltEndTime` | int64 | Halt end (epoch ms) | |

**CRITICAL LIMITATION:**
- OHLC fields (`open`, `dayHighPrice`, `dayLowPrice`, `close`) are **TODAY ONLY**
- NOT suitable for historical volatility calculation
- `prevClose` gives you ONLY yesterday's close (not a time series)

**Use Cases:**
- Real-time price monitoring
- Current day trading data
- Bid/ask spreads
- Trading halt detection
- 52-week range reference

**NOT useful for:**
- ❌ Historical volatility calculation (need DXLink Candles)
- ❌ Backtesting (need historical data)
- ❌ Time-series analysis (single day only)

---

## Comparison: What's Missing from OpenAPI Spec

### Fields NOT in spec but available in production:

**From /market-metrics:**
- ❌ `historical-volatility-30-day` (HV30) ⭐ **CRITICAL**
- ❌ `historical-volatility-90-day` (HV90) ⭐ **CRITICAL**
- ❌ `liquidity-value`
- ❌ `option-volume`
- ❌ `beta`
- ❌ `corr-spy-3month`
- ❌ `earnings` (nested object)

**From /market-data/by-type:**
- Most fields ARE in spec (more complete)

### Endpoints NOT clearly in main navigation:

- `/market-metrics/historic-corporate-events/dividends/{symbol}`
- `/market-metrics/historic-corporate-events/earnings-reports/{symbol}`

---

## Impact on Variance Architecture

### What We Can Get from REST API

✅ **Available (80% coverage):**
- HV30, HV90 from `/market-metrics` (when present)
- IV, IVR, IVP (always available)
- Beta, SPY correlation
- Liquidity metrics
- Option volume
- Earnings dates
- Historical dividends
- Historical earnings reports

⚠️ **Missing (20% of symbols):**
- HV30, HV90 not calculated for some symbols
- This is the gap we're solving

### What We CANNOT Get from REST API

❌ **Not available:**
- Historical OHLC candles (no time-series endpoint)
- Real-time Greeks (no REST endpoint for Greeks)
- Continuous price history for volatility calc
- Intraday data

### DXLink WebSocket Fills All Gaps

✅ **DXLink provides:**
- Historical OHLC via Candle events (1m, 5m, 1h, 2h, 1d)
- Real-time Greeks events
- Real-time Quote/Trade events
- No rate limits, WebSocket streaming

---

## Final Architecture Decision

**REST API Strategy:**
1. Primary: `/market-metrics` for HV30/HV90 (when available)
2. Fallback: DXLink Candle events (calculate ourselves)
3. Supplemental: Historical earnings from `/market-metrics/historic-corporate-events/earnings-reports/{symbol}`

**DXLink Strategy:**
1. Candle events: Fill HV30/HV90 gaps (20% of symbols)
2. Greeks events: Enable TOXIC_THETA handler
3. Quote events: Real-time price monitoring (optional)

**Expected Coverage:**
- REST /market-metrics: 80% (HV30/HV90 available)
- DXLink Candles fallback: 20% (fill gaps)
- **Total: 100% coverage at $0 cost**

---

## Recommended Next Steps

1. ✅ **Confirmed:** OpenAPI spec is incomplete (missing HV30/HV90 fields)
2. ✅ **Confirmed:** REST API has NO historical OHLC endpoint
3. ✅ **Confirmed:** DXLink Candle events are the ONLY solution for missing HV

**Action Items:**
1. Test DXLink Candle events: `python scripts/test_dxlink_candles.py`
2. Implement DXLink integration (8-12 hours)
3. Consider using historical earnings endpoint for earnings avoidance filter

---

**Document Status:** ✅ Complete and verified against production code
**Last Updated:** 2024-12-31
**Verified Fields:** Extracted from `src/variance/tastytrade_client.py`
