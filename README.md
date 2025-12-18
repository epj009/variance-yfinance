# Variance: Systematic Volatility Engine

[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/) [![Architecture](https://img.shields.io/badge/architecture-MVC-forestgreen.svg)]() [![Output](https://img.shields.io/badge/output-JSON-lightgrey.svg)]()

Variance is a **Systematic Volatility Analysis Engine** designed to identify statistical edges in the options market using purely open-source data (yfinance). It operates on a strict Model-View-Controller (MVC) architecture, where Python scripts act as the "Model" (emitting raw JSON), and an LLM-based CLI acts as the "View/Controller" (rendering the TUI and providing strategic guidance).

## 🚀 Key Features

*   **🛡️ Coiled Spring Detection (`🗜️`)**: Automatically flags "Traps" where high Implied Volatility is driven by price compression rather than fear. Prevents buying into breakouts.
*   **📊 NVRP (Normalized Volatility Risk Premium)**: Calculates the exact "Insurer's Markup" you are collecting over recent realized volatility.
*   **🔥 Vol Bias**: Identifies structural edges where `IV > HV` on an annualized basis.
*   **🧘 Zero-Auth**: Uses `yfinance` for market data. No brokerage API keys required.

## 🛠️ Architecture

- **Model (Python)**: `scripts/*.py`. Pure data crunching. Outputs structured JSON.
- **View (CLI)**: Renders the "Capital Console" TUI, visualizes risk with ASCII charts, and provides human-readable triage.
- **Data Engine**: High-performance SQLite cache with WAL mode to respect API rate limits while maintaining speed.

## 🧠 Core Metrics & Logic

### 1. The "Vol Bias" (Structural Edge)
*   **Formula**: `IV30 / HV252`
*   **Goal**: Find assets that are expensive relative to their long-term behavior.
*   **Signal**: > 1.0 = **Rich** (`🔥`).

### 2. The "Compression Ratio" (Safety Shim)
*   **Formula**: `HV20 / HV252`
*   **Goal**: Detect "Coiled Springs" — assets that have stopped moving and are priming for a breakout.
*   **Signal**: < 0.75 = **Coiled** (`🗜️`).
*   **Action**: If Coiled, enforce **Defined Risk** (Iron Condors). Avoid Strangles.

### 3. NVRP (Tactical Edge)
*   **Formula**: `(IV30 - HV20) / HV20`
*   **Goal**: Measure the "Premium Markup" relative to *current* market conditions.
*   **Signal**: Positive % = You are selling over-priced insurance.

## 📦 Installation

```bash
# 1. Clone the repository
git clone https://github.com/epj009/variance-yfinance.git variance
cd variance

# 2. Create virtual environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 3. (Optional) Set up Gemini CLI for the interactive Persona
#    (Required only if you want the AI trading assistant features)
mkdir -p .gemini
cp variance-system-prompt.md .gemini/GEMINI.md
```

## 🚦 Usage

### 1. Portfolio Triage (Daily Routine)
Analyze your current positions for harvest targets, gamma risk, and mechanical defense.

**Step 1:** Export your positions from your broker (e.g., Tastytrade) to a CSV file in `positions/`.

**Step 2:** Run the engine.
```bash
./variance
```
*This wrapper script automatically finds the newest CSV in `positions/`, analyzes it, and launches the dashboard.*

### 2. Volatility Scanning
Scan your watchlist for new opportunities using the "Rich & Coiled" filter.

```bash
./venv/bin/python3 scripts/vol_screener.py
```
*Outputs JSON candidates with flags for Rich (`🔥`) and Coiled (`🗜️`).*

## ⚙️ Configuration

Control the engine's physics in `config/trading_rules.json`:

*   `vol_bias_rich_threshold`: Level to trigger "Fire" (Default: 1.0)
*   `compression_coiled_threshold`: Level to trigger "Clamp" (Default: 0.75)
*   `net_liquidity`: Your account size (used for risk sizing).

## 📂 Project Structure

*   `scripts/`: Python logic (Screener, Analyzer, Renderer).
*   `config/`: JSON rules and strategy definitions.
*   `positions/`: Place your portfolio CSV exports here.
*   `variance`: Main launcher script.

## ⚠️ Disclaimer
Variance is a research tool for quantitative analysis. It does not provide financial advice. Trading options involves significant risk.