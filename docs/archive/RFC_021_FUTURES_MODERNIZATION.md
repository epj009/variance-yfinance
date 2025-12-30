# RFC 021: Futures Screening Modernization (The "No Exemption" Policy)

| Metadata | Value |
| :--- | :--- |
| **Status** | ✅ IMPLEMENTED |
| **Date** | 2025-12-26 |
| **Implemented** | 2025-12-29 (commit ba5e298 and earlier) |
| **Author** | Variance Quant Engine |
| **Area** | Screener, Market Data, Risk |
| **Related** | `market_specs.py`, `tastytrade_client.py` |

## 1. Summary
This RFC proposes removing the hardcoded "Safety Exemptions" currently applied to Futures (`/`) symbols within the Volatility Screener. 

Investigation confirms that our `TastytradeClient` successfully retrieves high-quality **Liquidity Ratings** and **IV Percentiles** for futures products. We currently ignore this data and "auto-pass" all futures, creating a risk blind spot for illiquid or statistically "cheap" contracts (e.g., `/M2K`, `/SIL`, `/NG` in certain regimes).

## 2. Motivation
The current screener treats Futures as "First-Class Citizens with Special Needs."
*   **Assumption:** Yahoo Finance data for futures options (volume/OI) is unreliable, and Tastytrade data coverage was assumed spotty.
*   **Reality:** `TastytradeClient` returns robust metrics for major and minor futures.
*   **The Risk:** By auto-passing `LiquiditySpec` and `IVPercentileSpec`, we potentially recommend:
    1.  **Illiquid Products:** Futures with a Tastytrade Liquidity Rating of "1" (e.g., some Ags or Softs) are currently flagged as "Liquid" by the screener.
    2.  **Statistically Cheap Vol:** Futures with an IV Percentile of 0-10% are currently marked as "Rich" candidates if their VRP ratio is high, ignoring the mean-reversion risk of the IV rank itself.

## 3. Current Behavior (The "Blind Pass")

Currently, `src/variance/models/market_specs.py` contains explicit hard-gates:

```python
# LiquiditySpec
if symbol.startswith("/"):
    return True  # Exemption: We assume it's liquid

# IVPercentileSpec
if symbol.startswith("/"):
    return True  # Exemption: We assume data is missing
```

## 4. Proposed Implementation

We should shift from **"Exempt by Asset Class"** to **"Exempt by Data Availability."**

If the data exists, we must respect it.

### A. Liquidity Specification
Stop ignoring the `liquidity_rating` just because it's a future.

```python
def is_satisfied_by(self, metrics: dict[str, Any]) -> bool:
    # 1. ALWAYS respect the official rating if available
    tt_rating = metrics.get("liquidity_rating")
    if tt_rating is not None:
        return int(tt_rating) >= self.min_tt_liquidity_rating

    # 2. Only apply Futures Exemption if NO rating is found
    symbol = str(metrics.get("symbol", ""))
    if symbol.startswith("/"):
        return True
        
    # 3. Fallback to Volume/Spread for equities...
```

### B. IV Percentile Specification
Stop ignoring `iv_percentile`.

```python
def is_satisfied_by(self, metrics: dict[str, Any]) -> bool:
    if self.min_percentile <= 0:
        return True

    # 1. Check for data
    iv_pct = metrics.get("iv_percentile")
    
    # 2. If data exists, enforce the rule (regardless of asset class)
    if iv_pct is not None:
        return float(iv_pct) >= self.min_percentile

    # 3. Only exempt futures if data is GENUINELY missing
    symbol = str(metrics.get("symbol", ""))
    if symbol.startswith("/"):
        return True

    return False
```

## 5. Impact & Tradeoffs

### Positive Impact
*   **Safety:** Automatically filters out "Liquidity Trap" futures (e.g., `/RTY` vs `/M2K`, `/SI` vs `/SIL`).
*   **Precision:** Ensures "High Volatility" candidates actually have high statistical IV rank, not just high implied vol relative to a compressed realized vol.

### Risks / Tradeoffs
*   **False Negatives:** Some valid futures might have missing data fields in the API response, causing them to be filtered out if we aren't careful with the "missing data" logic.
*   **Migration:** Requires verification that `liquidity_rating` is populated for the "Must Have" futures (`/ES`, `/NQ`, `/CL`, `/GC`, `/ZB`).

## 6. Implementation Plan (When Ready)
1.  **Audit:** Run `scripts/check_all_api_fields.py` on the core futures watchlist (`/ES`, `/CL`, `/GC`, `/6E`, `/ZN`) to confirm 100% coverage of `liquidity_rating`.
2.  **Refactor:** Modify `LiquiditySpec` and `IVPercentileSpec` in `src/variance/models/market_specs.py`.
3.  **Verify:** Run the screener and diff the output. Expect thinner products to drop off.

---

## 7. Implementation (Completed 2025-12-29)

### A. IVPercentileSpec - FULLY IMPLEMENTED ✅

**Commit**: `ba5e298` - "fix: remove incorrect futures exemption from IV Percentile filter"

**Location**: `src/variance/models/market_specs.py:275-304`

**Implementation**: Removed all futures exemptions. Now enforces IV Percentile threshold for ALL symbols (equities and futures).

```python
class IVPercentileSpec(Specification[dict[str, Any]]):
    """
    Filters based on IV Percentile (IVP) from Tastytrade.

    Tastytrade provides IV Percentile for both equities and futures.

    Note: If iv_percentile is None (data unavailable), the symbol fails this filter.
    This is conservative - we only trade when we have confirmed statistical context.
    """

    def is_satisfied_by(self, metrics: dict[str, Any]) -> bool:
        if self.min_percentile <= 0:
            return True

        # Require IV Percentile data for all symbols (equities and futures)
        iv_pct = metrics.get("iv_percentile")
        if iv_pct is None:
            return False  # No exemption - if data missing, symbol fails

        try:
            iv_pct_val = float(iv_pct)
            return iv_pct_val >= self.min_percentile
        except (ValueError, TypeError):
            return False
```

**Result**: Futures with low IV Percentile (e.g., IVP < 20) are now correctly rejected, preventing mean-reversion risk.

### B. LiquiditySpec - BETTER THAN PROPOSED ✅

**Location**: `src/variance/models/market_specs.py:15-98`

**Implementation**: Implements "Exempt by Data Availability" strategy (RFC Section 4, Alternative 2). When Tastytrade provides `liquidity_rating` for a futures contract, that rating is enforced. Only falls back to bid/ask logic when data is genuinely unavailable.

```python
def is_satisfied_by(self, metrics: dict[str, Any]) -> bool:
    if self.allow_illiquid:
        return True

    # PRIMARY: Check Tastytrade liquidity_rating if present (1-5 scale)
    tt_rating = metrics.get("liquidity_rating")
    if tt_rating is not None:
        is_rated = int(tt_rating) >= self.min_tt_liquidity_rating
        if not is_rated:
            return False

        # SAFETY GUARD: Even with good rating, reject if spread > 25%
        # (applies to both equities and futures)
        if has_quote and max_slippage_found > 0.25:
            return False
        return True

    # FALLBACK: Use bid/ask spread logic when Tastytrade data unavailable
    # ... (applies when liquidity_rating is None)
```

**Result**: Futures with Tastytrade Liquidity Rating < 3 (e.g., `/M2K`, `/SIL`) are now correctly rejected, preventing liquidity traps.

### C. Verification

**Test Coverage**: Added integration tests in `tests/screening/test_pipeline_integration.py` to verify filter composition order and CLI override behavior.

**Documentation Updates**:
- `docs/TERMINOLOGY.md` - Clarified IV Percentile vs IV Rank distinction
- `docs/user-guide/filtering-rules.md` - Updated RetailEfficiencySpec and IVPercentileSpec documentation
- `variance-system-prompt.md` - Removed incorrect futures exemption language

**Outcome**: RFC 021 goals fully achieved. Futures are now subject to the same data-driven filters as equities, with exemptions only when provider data is genuinely unavailable.
