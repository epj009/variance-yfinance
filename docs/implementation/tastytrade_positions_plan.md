# Implementation Plan: Tastytrade Positions Ingestion

## 0) Objective
Replace CSV-based portfolio ingestion with direct Tastytrade API positions data. The goal is to pull live positions and balances, normalize them into Variance's internal `Position` model, and preserve all triage/screener outputs with minimal behavioral changes.

---

## 1) Scope & Principles

**In scope**
- Fetch account(s) and positions via Tastytrade REST API.
- Normalize positions into existing `Position` model schema.
- Replace CSV lookup in `./variance` launcher and `analyze_portfolio` flow.
- Preserve existing strategy clustering and triage behavior.

**Out of scope (for now)**
- Multi-account aggregation rules.
- Trade execution or order management.
- Portfolio history/performance tracking.

---

## 2) Candidate Endpoints (To Confirm)

Likely Tastytrade REST endpoints (exact paths must be validated):
- `GET /accounts`
- `GET /accounts/{account_id}/positions`
- `GET /accounts/{account_id}/balances`
- `GET /accounts/{account_id}/transactions` (optional)

**Notes**
- Use OAuth env vars (`TT_CLIENT_ID`, `TT_CLIENT_SECRET`, `TT_REFRESH_TOKEN`, `API_BASE_URL`).
- Decide default account selection (first account vs config override).

---

## 3) Data Normalization Mapping

Map Tastytrade position fields into the current `Position` model:

**Position fields required by Variance**
- `symbol`
- `asset_type`
- `quantity`
- `strike`
- `dte`
- `exp_date`
- `call_put`
- `underlying_price`
- `pl_open`
- `cost`
- `delta`, `beta_delta`
- `theta`, `gamma`, `vega`
- `bid`, `ask`, `mark`

**Normalization strategy**
- Build a new adapter: `Position.from_api_row()` or `PositionAdapter`.
- Convert broker-specific symbols to roots using existing `get_root_symbol()`.
- Ensure futures symbols are normalized (`/ESZ5` → `/ES`).

---

## 4) Integration Points

**Primary pipeline**
- `src/variance/analyze_portfolio.py`
  - Replace CSV parse step with API fetch.
- `src/variance/portfolio_parser.py`
  - Keep for backward compatibility (optional), but default path should be API.
- `variance` launcher
  - Remove auto-detection of `positions/*.csv`.
  - Add API health checks and friendly error if auth missing.

**Optional**
- Add CLI flag to force CSV fallback (if needed for offline testing).

---

## 5) Engineering Tasks (Phased)

### Phase 1: API Client and Account Selection
- Implement minimal Tastytrade API wrapper for accounts + positions.
- Add config override for `default_account_id`.

### Phase 2: Position Normalization
- Build adapter that maps API positions to `Position`.
- Add tests with mocked API payloads.

### Phase 3: Pipeline Integration
- Wire positions fetch into `analyze_portfolio`.
- Update launcher to use API by default.
- Preserve demo mode (`./variance --demo`).

### Phase 4: Observability
- Add diagnostics if positions call fails or returns empty.
- Expose counts: positions fetched, positions normalized.

---

## 6) Open Issues & Risks
- Field mapping uncertainty (exact Tastytrade payload shape not confirmed).
- Multi-account support and account selection rules.
- Permissions/entitlement differences across accounts.

---

## 7) Acceptance Criteria
- `./variance` runs without CSV present, using live positions.
- Triage output matches prior CSV-based results for same portfolio.
- Clear error if API credentials are missing or invalid.

---

## 8) Contractor Notes
- Do not store secrets in repo.
- Use env vars for OAuth credentials.
- Keep CSV parser as optional fallback until API flow is validated.
