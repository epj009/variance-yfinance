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
- **Liquidity logic**: Defaults to ATM volume ≥ 50. Illiquid names are allowed if `Vol Bias > 1.2` (extreme edge).
- **Concentration defense**: Supports `--exclude-symbols` to avoid stacking risk; sector/asset-class filters remain.

### `scripts/analyze_portfolio.py` (Triage)
- **Output**: Raw JSON with `action_code` enums (`HARVEST`, `DEFENSE`, `GAMMA`, `ZOMBIE`, `EARNINGS_WARNING`, or `None`), `dte` ints, `pl_pct` ratios, `is_stale` flags.
- **Strategy-Aware**: Applies strategy-specific profit targets and gamma thresholds from `config/strategies.json` (e.g., 50% for Strangles, 25% for Butterflies).
- **Aggregation fix**: Ignores "Total" rows to prevent double-counting Beta Delta.
- **Metrics**: Computes Friction Horizon (days of theta to clear spread costs) and Delta/Theta Ratio.

## Installation
```bash
# 1. Create virtual environment and install dependencies
python3 -m venv venv
./venv/bin/pip install -r requirements.txt

# 2. Set up Gemini CLI persona (for interactive ./variance sessions)
cp variance-system-prompt.md .gemini/GEMINI.md
```

**Note:** The `variance-system-prompt.md` file defines the Variance trading persona. Copying it to `.gemini/GEMINI.md` enables the persona when running `./variance` interactively, while keeping MCP Gemini calls (used by Claude Code agents) persona-free for pure architect/developer/qa work.

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

## Key Metrics
- **Vol Bias**: `IV30 / HV252`
- **Bat's Efficiency Zone**: Price $15–$75 AND Vol Bias > 1.0
- **Friction Horizon**: `Total Liquidity Cost / Daily Portfolio Theta`

## Configuration
- `config/system_config.json`: Cache DB path, TTLs.
- `config/market_config.json`: Symbol map, sector overrides, futures proxies, skip lists.
- `config/trading_rules.json`: Vol Bias thresholds, DTE gates, profit targets, delta limits, Bat's zone parameters.
- `config/strategies.json`: Strategy-specific management rules (profit targets, gamma DTEs, defense mechanics) for 30+ option strategies.

## Notes
- Models emit raw JSON only; all rendering lives in the system prompt (View/Controller).
- Data hygiene is strict: zero-liquidity chains are rejected, IV units auto-corrected, DTE window enforced.
- Illiquid scanner overrides are explicit; use `--show-illiquid` plus `Vol Bias > 1.2` to surface edge cases.
