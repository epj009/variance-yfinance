# Variance: Systematic Volatility Engine

## Overview
**Variance** is a CLI-based options trading analysis system designed to automate the mechanical trading philosophy of Tastytrade/Tastylive. It helps retail traders separate luck from skill by analyzing portfolio mechanics and hunting for high-probability premium-selling opportunities.

## Quick Start (The Easy Way)
The project includes a smart wrapper script (`variance`) that handles environment setup and dependencies automatically.

**Note:** By default, all tools output **JSON** for easy integration with other tools or agents. For human-readable reports, use the `--text` flag.

1. **Auto-Analyze (Daily Routine):**
   ```bash
   # Text Report (for humans)
   ./variance --text
   
   # JSON Output (default)
   ./variance
   ```
   *Detects the latest portfolio export in `positions/` and runs the triage report.*

2. **Volatility Screener:**
   ```bash
   # Screen for opportunities (Text format)
   ./variance screen --text
   
   # Screen with limit (e.g., top 10)
   ./variance screen --text 10
   ```
   *Scans the default watchlist for opportunities.*

3. **Manual Triage:**
   ```bash
   ./variance triage positions/my_specific_export.csv --text
   ```

## Quick Start (The Manual Way)
- Create a virtualenv: `python3 -m venv venv`
- Install deps: `./venv/bin/pip install -r requirements.txt`
- Run tools using the explicit binary:
  ```bash
  # Run Triage
  ./venv/bin/python3 scripts/analyze_portfolio.py positions/<file>.csv --text
  
  # Run Screener
  ./venv/bin/python3 scripts/vol_screener.py --text
  ```

## Agent/CI Friendly Tests
- The test suite stubs external data for core logic (screener/triage) to avoid live market calls.
- Network helpers are marked skipped by default; CI can run `python -m pytest -q` without internet.

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

### 2. Portfolio Triage (Portfolio Health)
The `analyze_portfolio.py` script automates the daily "check-up", generating a comprehensive report on portfolio mechanics:

*   **Grouping:** Intelligent clustering of Stock and Option legs into named strategies. Detects Defined Risk (Condors, Verticals), Undefined Risk (Strangles, Jade Lizards), Time Spreads (Calendars), and Stock-Hedged positions (Covered Calls).
*   **Status Checks:**
    *   🌾 **Harvest:** Profit > 50%? Close it.
    *   🛡️ **Defense:** Tested & < 21 DTE? Roll it.
    *   ☢️ **Gamma:** < 21 DTE & Loser? Close it.
    *   🪦 **Dead Money:** Low Vol & Flat P/L? Kill it.
*   **Friction Horizon (Φ):** A "Velocity Brake" metric. Calculates how many days of Theta decay are required just to pay for the bid/ask spread slippage to exit.
    *   **Liquid:** < 1 Day.
    *   **Sticky:** 1-3 Days.
    *   **Liquidity Trap:** > 3 Days (Stop opening new trades).
*   **The Stress Box:** A scenario simulator that estimates portfolio P/L under various market conditions (Crash -5%, Rally +5%) based on your Beta-Weighted Delta.
*   **Delta Spectrograph:** Visualizes which specific positions are contributing the most directional risk (Delta) to your portfolio.
*   **Portfolio Theta:** Calculates daily Theta decay and provides a health check against Net Liquidity targets (0.1%-0.5% of Net Liq/day).
*   **Sector Allocation:** Warns if any single sector constitutes > 25% of the portfolio to reduce correlation risk.
*   **Asset Mix:** Calculates portfolio allocation across asset classes (Equity, Commodity, Fixed Income, FX, Index) and warns if Equity exposure exceeds 80% (correlation risk).

### 3. Liquidity Safety Layer
The system actively protects against "Slippage Tax" by analyzing market width and volume:
*   **Slippage Calculation:** Estimates the cost to enter/exit based on Bid/Ask spread width.
*   **Liquidity Gates:**
    *   **Vol Screener:** Filters out symbols with wide spreads (> 5% of price) or low ATM volume unless explicitly requested (`--show-illiquid`).
    *   **Triage:** Flags existing positions with `[LIQUIDITY WARNING]` if spreads widen, signaling execution risk.

## Configuration
The system is driven by centralized configuration files in the `config/` directory:

*   **`config/market_config.json`**: Defines the "Trading Universe". Contains:
    *   `SYMBOL_MAP`: Maps broker symbols (e.g., `/ES`) to data provider symbols (e.g., `ES=F`).
    *   `SECTOR_OVERRIDES`: Manual sector assignments for ETFs and Futures.
    *   `FUTURES_PROXY`: Logic for using ETF options (e.g., `USO`) as IV proxies for futures (`/CL`).
    *   `ASSET_CLASS_MAP`: Groups sectors into asset classes (Equity, Commodity, Fixed Income, FX, Index) for correlation tracking.
*   **`config/trading_rules.json`**: Defines the "Strategy Logic". Contains adjustable thresholds for:
    *   Net Liquidity (`$50,000`)
    *   Vol Bias (`0.85`)
    *   Profit Taking (`50%`)
    *   DTE Gates (`21` days)
    *   Portfolio Delta Limits (`+75` / `-50`)
    *   Theta/Net Liquidity targets (`0.1%`-`0.5%`)
    *   **Bat's Efficiency Zone:** Price $15-$75, Vol Bias > 1.0.
*   **`config/system_config.json`**: Defines system paths and cache settings (watchlist location, cache TTLs).

## Tools & Scripts

### `scripts/vol_screener.py`
*   **Purpose:** Scans a watchlist to find the best premium-selling candidates.
*   **Usage:** 
    ```bash
    python3 scripts/vol_screener.py [--text] [limit] [--show-all] [--show-illiquid] \
            [--exclude-sectors "Sector1,Sector2"] \
            [--include-asset-classes "Commodity,FX"]
    ```
*   **Features:**
    *   **Default Output:** JSON (use `--text` for human-readable table).
    *   Multi-threaded scanning (fast).
    *   Calculates Vol Bias on the fly using `HV252`.
    *   Filters and ranks symbols by "Richness" based on `trading_rules.json`.
    *   Uses proxies for futures (e.g., `/CL` via USO, `/ES` via VIX) and labels them in the output.
    *   Labels “🦇 Bat's Efficiency Zone” when price is between `$15-$75` and Vol Bias > `1.0`.
    *   **Sector Exclusion:** Can filter out symbols from specified sectors using `--exclude-sectors`.
    *   **Liquidity Filtering:** Automatically excludes illiquid symbols (wide spreads, low volume) to prevent bad fills.
    *   **Visual Signals:** Flags "🚱" (Illiquid) or "⚠️" (Wide Spread) in output.
*   **Asset Class Filtering:** Can filter by asset class using `--include-asset-classes "Commodity,FX"` or `--exclude-asset-classes "Equity"` for targeted rebalancing.
*   **Watchlist:** `watchlists/default-watchlist.csv` (first column `Symbol`).

### `scripts/analyze_portfolio.py`
*   **Purpose:** Diagnoses your current open positions.
*   **Usage:** 
    ```bash
    python3 scripts/analyze_portfolio.py [positions/your_export.csv] [--text]
    ```
*   **Features:**
    *   **Default Output:** JSON (use `--text` for human-readable report).
    *   Parses `util/sample_positions.csv` (Tastytrade export format) or specified file.
    *   **Triage Logic:** Applies the Harvest, Defense, Gamma, and Friction mechanics defined in "Core Logic" (above).
    *   **Risk Analysis:** Performs Portfolio Delta, Theta, and Sector/Asset correlation checks.
    *   **Liquidity Health:** Flags "Sticky" or "Trap" positions using the Friction Horizon (Φ) metric.

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
1.  **Routine:** Export positions to CSV (see `util/sample_positions.csv` for format). Run `./variance --text`.
2.  **Rebalance:** If portfolio delta is skewed, sector concentration is high, or asset mix shows Equity > 80%, run `./variance screen --text` with appropriate filters:
    *   Use `--exclude-sectors "Technology,Healthcare"` to avoid concentrated sectors.
    *   Use `--include-asset-classes "Commodity,FX"` to target non-equity opportunities for correlation defense.
3.  **Execution:** Use the "Vol Bias" report to select the most expensive premium to sell.

## Operational Notes
- Broker format: assumes Tastytrade exports. `Call/Put` casing is normalized internally, but supply the standard columns from Tastytrade for best results.
- Config resilience: both scripts ship with safe defaults. If `config/trading_rules.json` or `config/system_config.json` are missing, the tools fall back to baseline thresholds and a small watchlist (`SPY/QQQ/IWM`) so the CLI keeps working.
- Sectors: futures/indices are labeled explicitly (“Futures” / “Index”) and sector overrides take precedence over any provider lookups.