# Variance: Systematic Volatility Engine

[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/) [![Architecture](https://img.shields.io/badge/architecture-MVC-forestgreen.svg)]() [![Output](https://img.shields.io/badge/output-JSON-lightgrey.svg)]()

Variance is a **Systematic Volatility Analysis Engine** designed to identify statistical edges in the options market using purely open-source data (yfinance). It operates on a strict Model-View-Controller (MVC) architecture, providing industry-standard quantitative resolution for retail traders.

## 🚀 Key Features

*   **📡 Dual-VRP Synthesis**: Monitors both **Structural (252d)** and **Tactical (20d)** Volatility Risk Premia to find high-conviction trades.
*   **💎 Alpha-Theta Metrics**: Visualizes the "Quality of Income" by adjusting raw Theta for the current VRP markup (`Raw → Expected`).
*   **🧠 Strategist Workflow**: The Agent interprets mathematical states (e.g., "Bound") using the official Strategy Playbook and Mechanics documents.
*   **🛡️ Portfolio Triage**: Automatically flags positions for `HARVEST`, `DEFENSE`, `GAMMA`, or `ZOMBIE` based on mechanical rules.
*   **🧪 Research Lab**: Includes institutional-grade utilities for Sector Z-Score analysis and Tactical/Structural divergence.
*   **⚫ Monochrome UI**: A distraction-free, high-contrast terminal interface optimized for rapid information processing.

## 🛠️ Architecture

- **Model (Python)**: `scripts/*.py`. Pure data crunching. Outputs structured JSON.
- **View (CLI)**: Renders the "Capital Console" TUI, visualizes risk with ASCII charts, and provides human-readable triage.
- **Data Engine**: High-performance SQLite cache with WAL mode to respect API rate limits while maintaining speed.

## 🧠 Core Metrics & Logic

### 1. VRP Structural (Strategic Regime)
*   **Formula**: `IV30 / HV252`
*   **Goal**: Answers: *"Is volatility expensive relative to its yearly average?"*
*   **Signal**: > 1.0 = **Rich Regime**.

### 2. VRP Tactical (Trade Edge)
*   **Formula**: `IV30 / HV20` (Ratio) or `(IV30 - HV20) / HV20` (Net %)
*   **Goal**: Answers: *"Is volatility expensive relative to the last month of movement?"*
*   **Signal**: Positive % = You are selling over-priced insurance.

### 3. Alpha Theta (Expected Yield)
*   **Formula**: `Raw Theta * VRP_Tactical`
*   **Goal**: Measure the "Real P/L" of decay. If VRP is 1.5, every $1.00 of theta is "worth" $1.50 in expected value.

### 4. The "Signal" Logic (Regime Detection)
The system synthesizes multiple metrics into a single "Signal" for the TUI:

| Signal | Meaning | Target Environment |
| :--- | :--- | :--- |
| **RICH** | High Tactical VRP (>+20%) | Undefined Risk (Strangles) |
| **BOUND** | Squeezed / Rangebound | Defined Risk (Iron Condors) |
| **DISCOUNT** | Underpriced Vol (<-10%) | Long Vol (Calendars/Diagonals) |
| **EVENT** | Binary event risk | Earnings (Avoid) |
| **FAIR** | Fairly priced risk | Pass |

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
```bash
./variance
```
*Wrapper script that finds the newest CSV in `positions/`, analyzes it, and launches the dashboard.*

### 2. Volatility Scanning
```bash
./venv/bin/python3 scripts/vol_screener.py
```
*Outputs a ranked list of opportunities with side-by-side VRP(S) and VRP(T) metrics.*

### 3. Quant Research Lab
```bash
python3 util/research_lab.py
```
*Deep-dive utility for Sector Z-Scores and Portfolio Alpha-Theta quality audit.*

## ⚙️ Configuration

Control the engine's physics in `config/trading_rules.json`:

*   `vrp_structural_threshold`: Level to trigger "Neutral" (Default: 0.85)
*   `vrp_tactical_cheap_threshold`: Level to trigger "Discount" (Default: -0.10)
*   `net_liquidity`: Your account size (used for risk sizing and Alpha calculations).

## ⚠️ Disclaimer
Variance is a research tool for quantitative analysis. It does not provide financial advice. Trading options involves significant risk.