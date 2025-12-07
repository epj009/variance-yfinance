# The Alchemist's Lab: Project Documentation

## Overview
The "Alchemist" is a CLI-based trading assistant designed to automate the mechanical trading philosophy of *The Unlucky Investor's Guide to Options Trading* (Tastytrade style). It helps retail traders separate luck from skill by analyzing portfolio mechanics and hunting for high-probability trades.

## Quick Start
- Create a virtualenv: `python3 -m venv venv && source venv/bin/activate`
- Install deps: `pip install -r requirements.txt`
- Run the tools:
  - Screener: `python scripts/vol_screener.py [LIMIT] [--show-all] [--exclude-sectors "Sector1,Sector2"]`
  - Triage: `python scripts/analyze_portfolio.py positions/<tastytrade_export>.csv`
- Run tests: `python -m pytest -q`

## Core Logic & Innovation

### 1. Vol Bias (The "Richness" Metric)
Since reliable "IV Rank" data is often behind paywalls, we engineered a custom metric called **Vol Bias** to identify when options are expensive.

*   **Formula:** `Vol Bias = IV30 / HV252`
    *   **IV30:** Implied Volatility of At-The-Money (ATM) options ~30 days out.
    *   **HV252:** Annualized Realized Volatility (Standard Deviation of Log Returns) over the past 252 trading days (approx. 1 year).
*   **Interpretation:**
    *   **> 1.0 (Rich):** The market is pricing in *more* movement than the stock has actually realized in the past year. This is the "Fear Premium" we want to sell.
    *   **< 1.0 (Cheap):** The market is complacent. Selling premium here is dangerous (low reward for the risk).
    *   **Target:** We hunt for symbols with **Vol Bias > 0.85** (and ideally > 1.0).

### 2. Morning Triage (Portfolio Health)
The `analyze_portfolio.py` script automates the daily "check-up":
*   **Grouping:** Automatically groups individual option legs into complex strategies (Iron Condors, Strangles, etc.).
*   **Status Checks:**
    *   🌾 **Harvest:** Profit > 50%? Close it.
    *   🛡️ **Defense:** Tested & < 21 DTE? Roll it.
    *   ☢️ **Gamma:** < 21 DTE & Loser? Close it.
    *   🪦 **Dead Money:** Low Vol & Flat P/L? Kill it.
*   **Portfolio Delta:** Sums Beta-Weighted Deltas to warn if you are "Too Long" (>75) or "Too Short" (<-50).
*   **Portfolio Theta:** Calculates daily Theta decay and provides a health check against Net Liquidity targets (0.1%-0.5% of Net Liq/day).
*   **Sector Allocation:** Warns if any single sector constitutes > 25% of the portfolio to reduce correlation risk.

## Configuration
The system is driven by centralized configuration files in the `config/` directory:

*   **`config/market_config.json`**: Defines the "Trading Universe". Contains:
    *   `SYMBOL_MAP`: Maps broker symbols (e.g., `/ES`) to data provider symbols (e.g., `ES=F`).
    *   `SECTOR_OVERRIDES`: Manual sector assignments for ETFs and Futures.
    *   `FUTURES_PROXY`: Logic for using ETF options (e.g., `USO`) as IV proxies for futures (`/CL`).
*   **`config/trading_rules.json`**: Defines the "Strategy Logic". Contains adjustable thresholds for:
    *   Net Liquidity (`$50,000`)
    *   Vol Bias (`0.85`)
    *   Profit Taking (`50%`)
    *   DTE Gates (`21` days)
    *   Portfolio Delta Limits (`+75` / `-50`)
    *   Theta/Net Liquidity targets (`0.1%`-`0.5%`)

## Tools & Scripts

### `scripts/vol_screener.py`
*   **Purpose:** Scans a watchlist to find the best premium-selling candidates.
*   **Features:**
    *   Multi-threaded scanning (fast).
    *   Calculates Vol Bias on the fly using `HV252`.
    *   Filters and ranks symbols by "Richness" based on `trading_rules.json`.
    *   Uses proxies for futures (e.g., `/CL` via USO, `/ES` via VIX) and labels them in the output.
    *   Labels “🦇 Bats Efficiency Zone” when price is between `$15-$75` and Vol Bias > `1.0`.
    *   **Sector Exclusion:** Can filter out symbols from specified sectors using `--exclude-sectors`.
*   **Usage:** `source venv/bin/activate && python3 scripts/vol_screener.py [LIMIT] [--show-all] [--exclude-sectors "Sector1,Sector2"]`
*   **Watchlist:** `watchlists/default-watchlist.csv` (first column `Symbol`).

### `scripts/analyze_portfolio.py`
*   **Purpose:** Diagnoses your current open positions.
*   **Features:**
    *   Parses `util/sample_positions.csv` (Tastytrade export format).
    *   Generates a Markdown table of actionable steps (Harvest, Defense, etc.) based on `trading_rules.json`.
    *   Flags stale prices, zero-cost-basis trades, and sector concentration risks.
*   **Usage:** `source venv/bin/activate && python3 scripts/analyze_portfolio.py [positions/your_export.csv]`

### `scripts/get_market_data.py`
*   **Purpose:** The engine room. Fetches raw data from Yahoo Finance.
*   **Features:**
    *   Loads symbol maps and sector overrides from `market_config.json`.
    *   Calculates HV252 and IV30 math, with option-chain guards to avoid runaway downloads.
    *   Provides proxy IV/HV for futures so Vol Bias is available even when chains are absent.
    *   Caches results in `.market_cache.db` with periodic pruning to keep the cache small.

### `util/`
*   **Purpose:** Contains helper scripts and internal development tools.
*   **Scripts:**
    *   `util/debug_yfinance.py`: For testing raw yfinance data fetching.
    *   `util/test_yfinance_direct.py`: For direct yfinance API calls.
    *   `util/explore_earnings.py`: For exploring earnings date fetching from yfinance.

## Workflow
1.  **Morning:** Export positions to CSV (see `util/sample_positions.csv` for format). Run `source venv/bin/activate && python3 scripts/analyze_portfolio.py positions/<latest>.csv`.
2.  **Rebalance:** If portfolio delta is skewed or sector concentration is high, run `source venv/bin/activate && python3 scripts/vol_screener.py` (using `--exclude-sectors` if applicable) to find contrarian candidates.
3.  **Execution:** Use the "Vol Bias" report to select the most expensive premium to sell.

## Operational Notes
- Broker format: assumes Tastytrade exports. `Call/Put` casing is normalized internally, but supply the standard columns from Tastytrade for best results.
- Config resilience: both scripts ship with safe defaults. If `config/trading_rules.json` or `config/system_config.json` are missing, the tools fall back to baseline thresholds and a small watchlist (`SPY/QQQ/IWM`) so the CLI keeps working.
- Sectors: futures/indices are labeled explicitly (“Futures” / “Index”) and sector overrides take precedence over any provider lookups.
