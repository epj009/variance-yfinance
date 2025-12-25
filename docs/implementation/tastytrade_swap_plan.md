# Implementation Plan: Tastytrade Data Swap (Tasty-First, yfinance Price/Returns Fallback)

## 0) Objective
Re-platform Variance to use Tastytrade for all volatility/liquidity/IV metrics (IV, IVR, IVP, HV30/HV90, liquidity rating/value), while allowing a minimal yfinance fallback for price and returns only (for triage, stress tests, and correlation). This document is a contractor-ready implementation plan. No production code changes are included here.

---

## 1) Scope & Principles

**In scope**
- Tastytrade `/market-metrics` as primary data source.
- Tasty-native VRP using HV30/HV90.
- Liquidity gates using Tastytrade liquidity metrics.
- Optional fallback to yfinance for price + returns only.
- Updated configs and documentation.

**Out of scope (for now)**
- DXLink streaming feed integration (blocked by entitlements).
- Full position ingestion via Tastytrade API (separate phase).
- Removing yfinance entirely (not feasible without price/returns source).

---

## 2) Data Mapping (Tastytrade → Variance)

**Tastytrade `/market-metrics` fields**
- `implied-volatility-index` → `iv` (convert to percent if decimal)
- `implied-volatility-index-rank` → `iv_rank`
- `implied-volatility-percentile` → `iv_percentile` (new)
- `historical-volatility-30-day` → `hv30` (new)
- `historical-volatility-90-day` → `hv90` (new)
- `liquidity-rating`, `liquidity-value` → liquidity gates
- `option-expiration-implied-volatilities` → optional enrichment
- `corr-spy-3month` → optional correlation proxy
- `earnings.expected-report-date` → `earnings_date`

**Fallback from yfinance (if needed)**
- `price`
- `returns` (for correlation)
- `hv20`, `hv252` (only if still needed; otherwise ignore)

---

## 3) New VRP Formulas (Tasty-Native)

- Structural VRP = IV / HV90
- Tactical VRP = IV / HV30

**Default thresholds (starter, to be tuned)**
- `vrp_structural_threshold = 0.80`
- `vrp_structural_rich_threshold = 0.95`
- `hv_floor_percent = 5.0`
- `vrp_tactical_cheap_threshold = -0.10`

**Normalization**
Tastytrade IV appears as decimal; HV30/HV90 are percent. Always scale IV to percent before VRP.

---

## 4) Tuning Checklist (Required Post-Swap)

1) Pull `IV`, `HV30`, `HV90`, `IVR`, `IVP` for full watchlist.
2) Compute distributions for `IV/HV30`, `IV/HV90`, `IVR`, `IVP`.
3) Match pass-rate to old thresholds (target similar count of candidates).
4) Validate known high-IV names still pass; low-vol traps remain rejected.
5) Check futures proxies for skew vs ETF proxies.

**Expected output format (for calibration):**
```
VRP Structural (IV/HV90) Distribution
  p05: 0.48  p10: 0.57  p25: 0.72  p50: 0.88  p75: 1.06  p90: 1.22  p95: 1.35
  Pass counts: >=0.75: 142  >=0.80: 118  >=0.85: 93  >=0.90: 72

VRP Tactical (IV/HV30) Distribution
  p05: 0.62  p10: 0.70  p25: 0.86  p50: 1.03  p75: 1.21  p90: 1.38  p95: 1.52
  Pass counts: >=0.95: 141  >=1.00: 120  >=1.05: 98  >=1.10: 76
```

---

## 5) Engineering Tasks (Phased)

### Phase 1: Provider & Data Layer (✅ Done)
- [x] Add `TastytradeProvider` as primary data source.
- [x] Pull `/market-metrics` for all symbols.
- [x] Normalize IV scale to percent; populate `hv30`, `hv90`, `iv_rank`, `iv_percentile`.
- [x] Merge yfinance fallback (price + returns only).

**Files**
- `src/variance/get_market_data.py`
- `src/variance/interfaces.py`
- `src/variance/tastytrade_client.py`
- `config/runtime_config.json`

### Phase 2: Screening & Specs Updates (✅ Done)
- [x] Update VRP formulas to use HV30/HV90.
- [x] Update LiquiditySpec to use Tastytrade `liquidity-rating`/`liquidity-value`.
- [x] Correlation gate: keep using yfinance returns; add optional `corr-spy-3month` enrichment.
- [x] Add IV Percentile (IVP) gate and separation from IV Rank.

**Files**
- `src/variance/models/market_specs.py`
- `src/variance/screening/enrichment/vrp.py`
- `config/trading_rules.json`

### Phase 3: Docs + Diagnostics (✅ Done)
- [x] Document new data source and VRP math.
- [x] Add warnings if price/returns fall back to yfinance.
- [x] Add tuning checklist to docs.
- [x] Update TUI to display IVP column.

**Files**
- `README.md`
- `docs/implementation/tastytrade_swap_plan.md`
- `src/variance/tui_renderer.py`

---

## 6) Open Issues & Risks
- DXLink entitlement likely blocking live quotes; `/market-metrics` lacks price.
- No REST quote endpoint found at `/market-data/quotes` or `/quotes`.
- If yfinance price fails after-hours, prices may be stale (cache mitigates this).

---

## 7) Acceptance Criteria
- Vol screener runs using Tastytrade IV/HV/IVR/IVP without yfinance for those fields.
- Structural/tactical VRP computed from HV90/HV30.
- Liquidity filtering uses Tastytrade rating/value when present.
- If yfinance is unavailable, system degrades gracefully (no crash).

---

## 8) Contractor Notes
- Use OAuth credentials from env vars: `TT_CLIENT_ID`, `TT_CLIENT_SECRET`, `TT_REFRESH_TOKEN`, `API_BASE_URL`.
- Do not store secrets in repo.
- Any new configs must go in `config/runtime_config.json` or `config/trading_rules.json`.
