# The Alchemist's Lab: Project Documentation

## Overview
The "Alchemist" is a CLI-based trading assistant designed to automate the mechanical trading philosophy of *The Unlucky Investor's Guide to Options Trading* (Tastytrade style). It helps retail traders separate luck from skill by analyzing portfolio mechanics and hunting for high-probability trades.

## Core Logic & Innovation

### 1. Vol Bias (The "Richness" Metric)
Since reliable "IV Rank" data is often behind paywalls, we engineered a custom metric called **Vol Bias** to identify when options are expensive.

*   **Formula:** `Vol Bias = IV30 / HV100`
    *   **IV30:** Implied Volatility of At-The-Money (ATM) options ~30 days out.
    *   **HV100:** Annualized Realized Volatility (Standard Deviation of Log Returns) over the past 100 trading days (approx. 1 year).
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

## Tools & Scripts

### `scripts/vol_screener.py`
*   **Purpose:** Scans a watchlist to find the best premium-selling candidates.
*   **Features:**
    *   Multi-threaded scanning (fast).
    *   Calculates Vol Bias on the fly.
    *   Filters and ranks symbols by "Richness".
    *   Uses proxies for futures (e.g., `/CL` via USO, `/ES` via VIX) and labels them in the output.
*   **Usage:** `source venv/bin/activate && python3 scripts/vol_screener.py [LIMIT] [--show-all]`
*   **Watchlist:** `watchlists/default-watchlist.csv` (first column `Symbol`).

### `scripts/analyze_portfolio.py`
*   **Purpose:** Diagnoses your current open positions.
*   **Features:**
    *   Parses `util/sample_positions.csv` (Tastytrade export format).
    *   Generates a Markdown table of actionable steps (Harvest, Defense, etc.).
    *   Flags stale prices and zero-cost-basis trades; Gamma caution applies even if P/L% is unknown.
*   **Usage:** `source venv/bin/activate && python3 scripts/analyze_portfolio.py [positions/your_export.csv]`

### `scripts/get_market_data.py`
*   **Purpose:** The engine room. Fetches raw data from Yahoo Finance.
*   **Features:**
    *   Maps Futures symbols (`/CL` -> `CL=F`).
    *   Calculates HV100 and IV30 math, with option-chain guards to avoid runaway downloads.
    *   Provides proxy IV/HV for futures so Vol Bias is available even when chains are absent.

## Workflow
1.  **Morning:** Export positions to CSV (see `util/sample_positions.csv` for format). Run `source venv/bin/activate && python3 scripts/analyze_portfolio.py positions/<latest>.csv`.
2.  **Rebalance:** If portfolio delta is skewed, run `source venv/bin/activate && python3 scripts/vol_screener.py` to find contrarian candidates.
3.  **Execution:** Use the "Vol Bias" report to select the most expensive premium to sell.
