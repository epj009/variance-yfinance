# Variance: Systematic Volatility Engine

[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/) [![Architecture](https://img.shields.io/badge/architecture-MVC-forestgreen.svg)]() [![Output](https://img.shields.io/badge/output-JSON-lightgrey.svg)]()

Variance is a **Systematic Volatility Analysis Engine** designed to identify statistical edges in the options market using purely open-source data (yfinance). It operates on a strict Model-View-Controller (MVC) architecture, where Python scripts act as the "Model" (emitting raw JSON), and an LLM-based CLI acts as the "View/Controller" (rendering the TUI and providing strategic guidance).

## 🚀 Key Features

*   **📡 Signal Synthesis**: Automatically synthesizes Vol Bias, NVRP, and Compression into a single, actionable regime signal (`RICH`, `BOUND`, `DISCOUNT`).
*   **🧠 Strategist Workflow**: The Agent interprets mathematical states (e.g., "Bound") using the official Strategy Playbook and Mechanics documents.
*   **🛡️ Coiled Spring Detection (`🗜️`)**: Prevents buying into breakout traps by detecting price compression.

*   **📊 NVRP Ranking**: Sorts opportunities by the **"Insurer's Markup"**—the premium you collect relative to actual movement.
*   **🧘 Zero-Auth**: Uses `yfinance` for market data. No brokerage API keys required.
*   **⚫ Monochrome UI**: A distraction-free, high-contrast terminal interface.

## 🛠️ Architecture

- **Model (Python)**: `scripts/*.py`. Pure data crunching. Outputs structured JSON.
- **View (CLI)**: Renders the "Capital Console" TUI, visualizes risk with ASCII charts, and provides human-readable triage.
- **Data Engine**: High-performance SQLite cache with WAL mode to respect API rate limits while maintaining speed.

## 🧠 Core Metrics & Logic

### 1. The "Vol Bias" (Structural Edge)
*   **Formula**: `IV30 / HV252`
*   **Goal**: Find assets that are expensive relative to their long-term behavior.
*   **Signal**: > 1.0 = **Rich**.

### 2. NVRP (Tactical Edge)
*   **Formula**: `(IV30 - HV20) / HV20`
*   **Goal**: Measure the "Premium Markup" relative to *current* market conditions.
*   **Signal**: Positive % = You are selling over-priced insurance.

### 3. The "Signal" Logic (Regime Detection)
The system synthesizes multiple metrics into a single "Signal" for the TUI. You (the Agent) interpret these signals into strategies:

| Signal | Meaning | Target Environment |
| :--- | :--- | :--- |
| **RICH** | High Premium, Expanding Vol. | Undefined Risk (Strangles) |
| **BOUND** | Price is squeezed / Rangebound. | Defined Risk (Iron Condors) |
| **DISCOUNT** | Options are underpriced. | Long Vol (Straddles/Calendars) |
| **EVENT** | Binary event risk. | Earnings (Avoid) |
| **FAIR** | Fairly priced risk. | Pass |

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
*Outputs a ranked list of opportunities sorted by NVRP (Markup), with specific strategy recommendations.*

## ⚙️ Configuration

Control the engine's physics in `config/trading_rules.json`:

*   `vol_bias_rich_threshold`: Level to trigger "Fire" (Default: 1.0)
*   `compression_coiled_threshold`: Level to trigger "Clamp" (Default: 0.75)
*   `nvrp_cheap_threshold`: Level to trigger "Discount" (Default: -0.10)
*   `net_liquidity`: Your account size (used for risk sizing).

## 📂 Project Structure

*   `scripts/`: Python logic (Screener, Analyzer, Renderer).
*   `config/`: JSON rules and strategy definitions.
*   `positions/`: Place your portfolio CSV exports here.
*   `variance`: Main launcher script.

## ⚠️ Disclaimer
Variance is a research tool for quantitative analysis. It does not provide financial advice. Trading options involves significant risk.
