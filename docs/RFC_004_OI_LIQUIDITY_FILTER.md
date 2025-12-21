# RFC 004: Open-Interest (OI) Liquidity Filtering

## 1. Summary
This RFC proposes switching the screener's liquidity gate from **ATM volume** to **ATM open interest (OI)** to better reflect tradeable liquidity, especially outside of market hours. The change is intended to align the "tradeable" flag with tastylive-style mechanics by using a more stable liquidity proxy at the selected DTE.

## 2. Motivation
* **Volume is fragile off-hours:** After hours/weekends, ATM volume often prints as zero even for liquid names, which artificially suppresses candidates.
* **OI is more stable:** OI is sticky and better reflects persistent liquidity; it is less sensitive to the clock.
* **Tradeable accuracy:** If the screener marks a name "tradeable," it should be based on liquidity that is still valid when a trader places a 45 DTE order.

## 3. Proposed Change
Replace the current liquidity rule:
* `ATM volume >= min_atm_volume`

With:
* `ATM open interest >= min_atm_open_interest`

Retain the slippage rule (bid/ask width) to prevent wide markets from passing.

### 3.1 Data Requirements
Extend `scripts/get_market_data.py` to compute and store:
* `atm_open_interest`: sum of ATM call + ATM put OI for the selected expiration.

This should use the same expiration selection logic as IV and ATM volume (closest to target DTE within the configured window).

### 3.2 Configuration
Add a new rule in `config/trading_rules.json` (with default in `scripts/config_loader.py`):
```json
"min_atm_open_interest": 500
```

Optional: add a `liquidity_mode` flag with values:
* `volume` (current behavior)
* `open_interest` (new behavior)
* `either` (pass if volume OR OI meets threshold)

## 4. Comparison to Current Volume Filtering
Bake-off results on the full 135-symbol watchlist, run on Saturday after hours:

* **Volume-based tradeable:** 16
* **OI-based tradeable:** 6
* **Overlap:** 6
* **Only-volume (dropped by OI):** 10

Only-volume examples:
`BAC`, `BIDU`, `GLD`, `LRCX`, `MSFT`, `RKLB`, `SLV`, `UNG`, `WFC`, `XOM`

OI-based tradeable list:
`/6C`, `/6J`, `/CL`, `/NG`, `/ZB`, `IBIT`

### Interpretation
* OI is **more conservative** in the current dataset.
* After-hours volume likely over-penalizes equities; OI should be less time-sensitive.
* Futures still pass more often due to proxy IV + no options-chain liquidity checks.

## 5. Operational Considerations
* **Timing:** Results should be re-evaluated Monday after open to remove weekend noise.
* **Futures:** Futures lack direct equity-style options chains in yfinance. Consider:
  * Keep futures exempt from OI filter (current behavior), or
  * Require real chain liquidity for "tradeable" designation.
* **Backwards compatibility:** Default to `volume` unless a new `liquidity_mode` is set.

## 6. Recommendation
**ADOPT** with a guarded rollout:
1) Add `atm_open_interest` to market data.
2) Add `min_atm_open_interest` config and `liquidity_mode` flag.
3) Re-run the bake-off during market hours and compare candidate stability.

This change should improve the "tradeable" flag’s reliability and align the system with 45-DTE execution mechanics.
