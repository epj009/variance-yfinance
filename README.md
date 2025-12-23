# Variance: Systematic Volatility Engine

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Philosophy: Tastylive](https://img.shields.io/badge/Philosophy-Tastylive-red.svg)](https://www.tastylive.com/)

**Variance** is a quantitative analysis engine designed for systematic options traders. It transforms raw market data and broker positions into an institutional-grade triage dashboard, focusing exclusively on **Price**, **Volatility**, and **Mechanics**.

Built on the Tastylive philosophy, Variance rejects market narratives in favor of statistical edge, specifically exploiting the **Volatility Risk Premium (VRP)** through net-premium selling strategies.

Variance uses institution-grade **Logarithmic Distance** for all volatility calculations, ensuring mathematical objectivity across different asset scales and price regimes.

---

## 🛠 Architecture & Standards

### 🧩 Modular Design
Variance has been refactored into a professional Python package structure:
- **`src/variance/`**: Core engine logic.
- **`src/variance/models/`**: Domain-driven objects (`Position`, `StrategyCluster`, `Portfolio`).
- **`src/variance/strategies/`**: Decoupled strategy pattern for specialized trade management.
- **`src/variance/get_market_data.py`**: Resilient data layer with a thread-safe SQLite (WAL) cache.

### 📐 The Quantitative Standard
Unlike retail tools that use arithmetic subtraction ($IV - HV$), Variance operates in **Logarithmic Space**.
- **Scale Symmetry**: A 1-point move in a low-vol asset has the same mathematical weight as a relative move in a high-vol asset.
- **Z-Score Foundational**: All signals are derived from how many units of historical movement the current price covers.
- **Stoic Logic**: "Subtraction is noise; Division is signal."

---

## 📊 The Dashboard

Variance provides a high-fidelity terminal interface (TUI) for real-time portfolio management and opportunity scanning.

```text
╭──────────────── THE CAPITAL CONSOLE ─────────────────╮
│ • Net Liq:  $50,000.00        • Open P/L: $1,110.00  │
│ • BP Usage: 38.1% (Deploy)    • Status:   Harvesting │
╰──────────────────────────────────────────────────────╯
╭────────────────────────────────────────────────────────────────────────────────────╮
│ THE GYROSCOPE (Risk)                         THE ENGINE (Exposure)                 │
│ • Tilt:      Neutral (+12 Δ)                 • Downside:  $-3,541.08 (Crash (-5%)) │
│ • Theta:     $198.00 → $253.62 (+28% VRP)    • Upside:    $2,858.92 (Rally (+5%))  │
│ • Stability: 0.06 (Stable)                   • Mix:       🌍 Diversified           │
│                                              • Data Qual: 100% (Excellent)         │
╰────────────────────────────────────────────────────────────────────────────────────╯
                                                                                    
📊 DELTA SPECTROGRAPH (Portfolio Drag)                                              
                                                                                    
      1     SPY            ┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃                                +12.50 Δ   
      2     /ES            ┃┃┃┃┃┃┃┃┃┃                                      -8.40 Δ   
      3     IWM            ┃┃┃┃┃┃                                          +5.20 Δ   
                                                                                    
📂 PORTFOLIO OVERVIEW
├── 🚨 ACTION REQUIRED (3)
│   ├── 💰 SPY (Iron Condor) $200.00 [HARVEST] 
│   │   └── 27 DTE: Profit 66.7% (Target: 50%)
│   ├── 🛡️ /ES (Short Strangle) $-800.00 [DEFENSE] 
│   │   └── 12 DTE: Tested & < 21 DTE
│   └── 🛡️ IWM (Short Put) $250.00 [GAMMA] 
│       └── 12 DTE: < 21 DTE Risk
```

---

## 🧠 Core Philosophy (The Variance Code)

Variance is engineered to enforce three primary mechanical pillars:

1.  **Sell Premium (The Edge):** We are net sellers of options to harvest time decay (Theta) and exploit the fact that implied volatility (IV) historically overstates actual movement (HV).
2.  **Alpha-Theta (The Engine):** We optimize for **Expected Yield**. Variance adjusts raw Theta for VRP to identify "Toxic Theta" (underpaid risk) vs. "Alpha Theta" (overpaid premium).
3.  **Law of Large Numbers:** We prioritize **Occurrences over Home Runs**. The system nudges you to "Trade Small, Trade Often" to allow probabilities to realize over hundreds of independent trades.

---

## 🚀 Key Features

### 📡 Dual-VRP Synthesis
Monitors both **Structural (252d)** and **Tactical (20d)** volatility regimes. The engine identifies dislocations where the cost of insurance is high relative to both long-term norms and immediate movement.

### 🛡️ Probabilistic Triage
Automatically flags positions using unified risk rules:
*   **💰 HARVEST:** Profit > 50% (Lock in winners).
*   **🛡️ DEFENSE:** Positions entering the 21-DTE Gamma Zone or breaching strikes.
*   **💀 TOXIC:** Negative expectancy trades where statistical cost > premium collected.
*   **🐳 SIZE RISK:** Individual positions contributing > 5% of Net Liq to a crash scenario.

### 🌀 Resilient Hybrid Proxies
To solve the "Data Blackout" problem in futures (CAD, Bonds, Oil), Variance employs a **Hybrid Idiosyncratic Model**:
*   **IV Numerator:** Pulled from liquid category benchmarks (`FXE`, `IEF`, `^VIX`).
*   **HV Denominator:** Pulled from the actual asset's idiosyncratic price history.
*   **Result:** Reliable, real-time "Rich/Cheap" signals even when specific ETF options are illiquid.

---

## 🏁 Getting Started

### Prerequisites
*   Python 3.10+
*   A CSV export of your positions (Standard Tastytrade/ThinkOrSwim format).

### Installation

```bash
# 1. Clone and Enter
git clone https://github.com/epj009/variance-yfinance.git variance
cd variance

# 2. Setup Environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 3. Configure Assistant (Optional)
mkdir -p .gemini
cp variance-system-prompt.md .gemini/GEMINI.md
```

---

## 🚀 Usage

### 1. Daily Portfolio Triage
The primary command for managing existing risk. It finds your latest CSV, runs the analysis pipeline, and renders the TUI.
```bash
./variance
```

### 2. Volatility Screener
Scan your watchlist for high-probability entries based on tactical VRP markups.
```bash
python3 scripts/vol_screener.py
```

### 3. Quantitative Research Lab
Run deeper audits on your portfolio's "Alpha-Theta" quality and sector concentration.
```bash
python3 util/research_lab.py
```

### 4. Showcase Demo
View the system's full capabilities using a pre-configured institutional showcase portfolio.
```bash
./variance --demo
```

---

## ⚙️ Customization

Variance is fully externalized. Tune your "Nightmare Scenarios" and trading thresholds in `config/trading_rules.json`:

*   **Net Liquidity:** Calibrates risk-sizing and whale-detection.
*   **DTE Windows:** Defaulted to **20–70 days** to capture entire monthly cycles.
*   **Liquidity Gates:** Defaulted to **Open Interest (OI)** for stability across all market hours.

---

## ⚠️ Disclaimer
Variance is a research and automation tool for quantitative analysts. **It does not provide financial advice.** Options trading involves significant risk of loss. The developers are not responsible for any financial outcomes resulting from the use of this software.
