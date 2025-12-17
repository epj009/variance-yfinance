# Variance: Systematic Volatility Engine

[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/) [![Architecture](https://img.shields.io/badge/architecture-MVC-forestgreen.svg)]() [![Output](https://img.shields.io/badge/output-JSON-lightgrey.svg)]()

Variance is now a strict Model-View-Controller (MVC) system. The Python layer (`scripts/*.py`) is **Model-only**: it emits raw JSON (floats, bools, enums) with zero presentation logic. The LLM/Agent is the **View/Controller**, rendering the “Variance Visual Language” (badges, ASCII charts) from the raw codes (e.g., `action_code: "HARVEST"` → `💰 [HARVEST]`).

## Architecture
- **Model (Python scripts)**: Pure data emitters. No text, emojis, or formatting. Outputs JSON for downstream rendering.
- **View/Controller (Agent prompt)**: Renders badges, ASCII charts, and human-readable guidance from raw fields and enums.
- **Data Engine**: `scripts/get_market_data.py` uses a high-performance SQLite cache (WAL, thread-local connections) and strict data hygiene to protect against bad feeds.

## Core Components

### `scripts/get_market_data.py` (Engine)
- **Performance**: WAL-mode SQLite with thread-local persistent connections (no connection thrashing).
- **Resilience**: Rejects zero-liquidity chains, auto-corrects IV units (decimal vs percent), enforces strict 25–50 DTE windows, and uses proxy IV/HV where configured.
- **Caching**: Never caches errors/None; lazy expiration with opportunistic pruning.

### `scripts/vol_screener.py` (Scanner)
- **Output**: Raw JSON with flags (`is_rich`, `is_fair`, `is_illiquid`, `is_earnings_soon`, `is_bats_efficient`).
- **Variance Score**: Ranks opportunities (0-100) using a weighted composite:
  - **IV Rank (40%)**: Is premium elevated?
  - **Structural Bias (30%)**: Is it historically expensive?
  - **Tactical Bias (30%)**: Is there a short-term edge?
  - **Penalty**: -50% for "Dead Zone" traps (High Bias + Low HV Rank).
- **Asset Lineage**: Prevents correlation stacking using `FAMILY_MAP` (e.g., holding `SLV` automatically flags `/SI` and `SIVR` as held).
- **Liquidity logic**: Defaults to ATM volume ≥ 50. Illiquid names are allowed if `Vol Bias > 1.2` (extreme edge).
- **Concentration defense**: Supports `--exclude-symbols` and Family logic to avoid stacking risk.

### `scripts/analyze_portfolio.py` (Triage)
- **Output**: Raw JSON with `action_code` enums (`HARVEST`, `DEFENSE`, `GAMMA`, `ZOMBIE`, `EARNINGS_WARNING`, or `None`), `dte` ints, `pl_pct` ratios, `is_stale` flags.
- **Strategy-Aware**: Applies strategy-specific profit targets and gamma thresholds from `config/strategies.json` (e.g., 50% for Strangles, 25% for Butterflies).
- **Aggregation fix**: Ignores "Total" rows to prevent double-counting Beta Delta.
- **Metrics**: Computes Friction Horizon (days of theta to clear spread costs) and Delta/Theta Ratio.

## Prerequisites
- **Python 3.10+**
- **[Gemini CLI](https://www.npmjs.com/package/@google/generative-ai-cli)** - Install via npm:
  ```bash
  npm install -g @google/generative-ai-cli
  ```
- **Google Account** - Authenticate Gemini CLI (free tier available):
  ```bash
  gemini auth
  ```

## Installation
```bash
# 1. Clone the repository
git clone https://github.com/epj009/options-alchemist.git variance
cd variance

# 2. Create virtual environment and install dependencies
python3 -m venv venv
./venv/bin/pip install -r requirements.txt

# 3. Set up Gemini CLI persona (for interactive ./variance sessions)
mkdir -p .gemini
cp variance-system-prompt.md .gemini/GEMINI.md
```

**Note:** The `variance-system-prompt.md` file defines the Variance trading persona. Copying it to `.gemini/GEMINI.md` enables the persona when running `./variance` interactively, while keeping MCP Gemini calls (used by Claude Code agents) persona-free for pure architect/developer/qa work.

## Optional: Tastytrade IV Rank Integration

To enable the three-factor filter with IV Rank (premium elevation timing), set up Tastytrade OAuth credentials:

```bash
# 1. Log into Tastytrade → Settings → OAuth Applications
# 2. Create new OAuth application
# 3. Add http://localhost:8000 as valid callback URL
# 4. Save the CLIENT_SECRET

# 5. Go to OAuth Applications → Manage → Create Grant
# 6. Save the REFRESH_TOKEN

# 7. Set environment variables (add to ~/.bashrc or ~/.zshrc for persistence)
export TASTY_CLIENT_SECRET='your_client_secret_here'
export TASTY_REFRESH_TOKEN='your_refresh_token_here'
```

**Without Tastytrade credentials**, the vol screener operates in **two-factor mode** (Vol Bias + HV Rank only), which still catches expansion traps but skips entry timing optimization.

## Quick Start

**First time setup - Add a portfolio:**
```bash
# Option A: Use the sample portfolio (for testing)
mkdir -p positions
cp util/sample_positions.csv positions/

# Option B: Export your own portfolio from Tastytrade
# Download CSV from Tastytrade → Positions → Export
# Save to positions/ directory
```

**Run Variance:**
```bash
# Interactive mode - Gemini analyzes latest portfolio and provides trading guidance
./variance

# Or run direct Python analysis (JSON output only)
./venv/bin/python3 scripts/analyze_portfolio.py positions/<your-file>.csv
```

The `./variance` script launches an interactive Gemini session that:
1. Automatically finds and analyzes your latest portfolio CSV
2. Identifies actionable trades (harvest winners, defend losers, gamma risks)
3. Screens for new volatility opportunities based on current IV/HV
4. Allows follow-up questions about specific positions or strategies

## Usage (Model commands)
- **Daily Triage**  
  ```bash
  ./venv/bin/python3 scripts/analyze_portfolio.py positions/<latest>.csv
  ```
- **Opportunity Scan**  
  ```bash
  ./venv/bin/python3 scripts/vol_screener.py
  ```
- **Concentration Defense**  
  ```bash
  ./venv/bin/python3 scripts/vol_screener.py --exclude-symbols "NVDA,TSLA"
  ```

### Key Metrics

### Three-Factor Entry Filter
The vol screener implements a comprehensive three-factor filter for optimal premium selling entries:

1. **Vol Bias > 1.0**: `IV30 / HV252` - Statistical edge (IV > HV)
2. **HV Rank > 15%**: Market activity filter (avoid dead markets)
3. **IV Rank > 30%**: Premium elevation filter (entry timing)

### Metric Definitions

- **Structural Vol Bias**: `IV30 / HV252` - Primary signal for rich premiums (Climate)
  - Measures long-term relative value: Is implied volatility higher than the last year's realized volatility?
  - **Purpose**: Identifies expensive asset classes (Structural Edge).
  - Threshold: 1.0

- **Tactical Vol Bias**: `IV30 / HV20` - Immediate entry signal (Weather)
  - Measures short-term mean reversion: Is implied volatility higher than the last month's realized volatility?
  - **Purpose**: Identifies "Fear Bubbles" where IV stays high despite price stabilizing (Tactical Edge).
  - Use case: Catching the post-earnings "crush" or mean reversion after a panic.

- **HV Rank**: Percentile of current 30-day HV vs 1-year rolling HVs (0-100%)
  - **Purpose**: Regime detection - Is the market active or dead?
  - **Short Vol Trap Detection**: Filters symbols with Vol Bias > 1.0 AND HV Rank < 15%
  - **Prevents**: Selling premium in crushed volatility regimes (expansion risk)
  - **Example**: /6A with Vol Bias 2.05 but HV Rank 5% = TRAP (market asleep)
  - **Configurable**: `hv_rank_trap_threshold` in `trading_rules.json` (default: 15%)
  - **Data Source**: Yahoo Finance (calculated locally, zero dependencies)

- **IV Rank**: Percentile of current IV vs 52-week IV range (0-100%)
  - **Purpose**: Entry timing - Are premiums elevated or cheap?
  - **Premium Elevation Filter**: Skips symbols with IV Rank < 30%
  - **Prevents**: Selling premium when it's at historic lows (wait for spike)
  - **Example**: /SI with HV Rank 86% but IV Rank 7% = WAIT (market moving, premiums cheap)
  - **Configurable**: `iv_rank_threshold` in `trading_rules.json` (default: 30%)
  - **Data Source**: Tastytrade API (optional, requires OAuth credentials)
  - **Graceful Degradation**: If Tastytrade unavailable, filter bypasses (two-factor mode)

- **Bat's Efficiency Zone**: Price $15–$75 AND Vol Bias > 1.0
- **Friction Horizon**: `Total Liquidity Cost / Daily Portfolio Theta`

## Configuration
- `config/system_config.json`: Cache DB path, TTLs.
- `config/market_config.json`: Symbol map, sector overrides, futures proxies, skip lists.
- `config/trading_rules.json`: Vol Bias thresholds, DTE gates, profit targets, delta limits, three-factor filter thresholds:
  - `vol_bias_rich_threshold`: 1.0 (IV > HV requirement)
  - `hv_rank_trap_threshold`: 15.0 (minimum market activity)
  - `iv_rank_threshold`: 30.0 (minimum premium elevation)
- `config/strategies.json`: Strategy-specific management rules (profit targets, gamma DTEs, defense mechanics) for 30+ option strategies.

## Notes
- Models emit raw JSON only; all rendering lives in the system prompt (View/Controller).
- Data hygiene is strict: zero-liquidity chains are rejected, IV units auto-corrected, DTE window enforced.
- Illiquid scanner overrides are explicit; use `--show-illiquid` plus `Vol Bias > 1.2` to surface edge cases.
