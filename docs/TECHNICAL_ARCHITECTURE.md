# Variance Engine: Technical Architecture

> **Version:** 1.2.0  
> **Date:** December 2025  
> **Status:** Production-Ready

This document provides a comprehensive technical overview of the **Variance Systematic Volatility Engine**. It details the internal logic, mathematical models, and data pipeline architecture for developers and quantitative analysts.

---

## 1. System Design Pattern (MVC)

Variance follows a strict **Model-View-Controller (MVC)** separation to ensure testability and clear separation of concerns.

*   **Model (The Truth):**  
    *   `scripts/analyze_portfolio.py`: Orchestrator.
    *   `scripts/triage_engine.py`: Business logic and risk rules.
    *   `scripts/vol_screener.py`: Market scanning and scoring logic.
    *   `scripts/get_market_data.py`: Data fetching and normalization.
*   **View (The Presentation):**  
    *   `scripts/tui_renderer.py`: Pure visualization. It takes the JSON output from the Model and renders it using the `rich` library. It contains **no** business logic.
*   **Controller (The User Interface):**  
    *   `variance` (CLI Entry point): Handles user commands and invokes the Model.
    *   `gemini` (AI Agent): Acts as the interactive "Strategist," interpreting Model output for the user.

---

## 2. The Data Layer (`get_market_data.py`)

The data pipeline is designed for **Resilience** and **Speed**. It does not rely on real-time sockets but uses a high-performance polling architecture with intelligent caching.

### 2.1. Optimized SQLite Cache
*   **Technology:** SQLite in **WAL (Write-Ahead Logging)** mode.
*   **Concurrency:** Thread-local connections allow multi-threaded fetching without locking issues.
*   **Persistence:** Data persists across sessions in `.market_cache.db`.

### 2.2. Resilience Strategies
1.  **Dynamic TTL (Time-To-Live):**
    *   *Market Hours (09:30-16:00):* Short TTL (10-15 mins) for freshness.
    *   *After Hours (16:00-09:30):* TTL extends automatically to **10:00 AM next day**. This bridges the overnight gap where Option Chains are unavailable, preventing "blank dashboard" syndrome.
2.  **Partial Data Mode:**
    *   If `yfinance` returns `Price` and `History` (HV) but fails to return `Option Chain` (IV) (common during maintenance windows):
    *   **Action:** The system returns a "Partial" record.
    *   **Flags:** `vrp_structural` = 0.0, `vrp_tactical` = 0.0.
    *   **Impact:** Position P/L and Delta are calculated; Volatility metrics are suppressed; Screener filters reject the symbol.

---

## 3. The Quantitative Engine (`triage_engine.py`)

This module applies the "Physics" of the Variance philosophy to raw positions.

### 3.1. VRP Markup (Alpha-Theta)
We quantify the "Quality of Income" by adjusting raw time decay for the Volatility Risk Premium (VRP).

$$ 	ext{AlphaTheta} = 	ext{Theta}_{	ext{Raw}} 	imes \left( \frac{\text{IV}_{\text{30}}}{\text{HV}_{\text{252}}} \right) $$ 

*   **Logic:** If you sell premium when IV (20%) > HV (15%), every $1.00 of Theta is statistically "worth" $1.33 in Expected Value.
*   **Toxic Theta:** If IV < HV, the multiplier is < 1.0. This flags the position as `TOXIC`—you are being underpaid for movement risk.

### 3.2. Dynamic Tail Risk
The engine is **label-agnostic**. It calculates the "Max Drawdown" based on the worst mathematical outcome of configured scenarios.

1.  **Ingest:** Load scenarios from `config/trading_rules.json` (e.g., "-5% Crash", "+10% Rally").
2.  **Simulate:** For each scenario, calculate Portfolio P/L:
    $$ P/L = (\Delta \times \text{Move}) + (0.5 \times \Gamma \times \text{Move}^2) + (\text{Vega} \times \text{VolShock}) $$ 
3.  **Select:** `Tail Risk = abs(min(All_Scenario_PLs))`
4.  **Status:**
    *   **Safe:** < 5% Net Liq
    *   **Loaded:** 5-15% Net Liq
    *   **Extreme:** > 15% Net Liq

### 3.3. Triage Hierarchy
Action codes are assigned based on a strict priority waterfall:

1.  **HARVEST:** `Profit % >= Target` (Default 50%) OR `Velocity Win` (>25% in <5 days).
2.  **SIZE_THREAT:** Tail Risk contribution > 5% Net Liq.
3.  **DEFENSE:** Tested (ITM) AND DTE < 21.
4.  **GAMMA:** Untested AND DTE < 21.
5.  **HEDGE_CHECK:** Position tagged as hedge, but Portfolio Delta is neutral/short (hedge maybe unnecessary).
6.  **TOXIC:** `VRP < 0.8` AND `P/L` is stagnant (Dead Money).
7.  **SCALABLE:** `VRP_Tactical` surge detected (> 1.5x) in a small position.

### 3.4. Data Quality Safeguards
To prevent yfinance data anomalies (e.g., 1% IV on a 100% IV stock) from corrupting the dashboard, the engine implements a dual-layer guardrail:

1.  **Portfolio Accounting (Clamping):** When aggregating total Alpha-Theta, individual VRP Tactical markups are clamped:
    *   **Floor:** -50% (Max penalty).
    *   **Ceiling:** +100% (Max bonus).
2.  **Transparency (Warning):** Individual positions displaying an absolute markup > 50% are tagged with a **⚠️ Data Quality Warning** in the TUI, prompting manual verification on the broker platform.

---

## 4. The Screener (`vol_screener.py`)

The screener synthesizes raw metrics into actionable "Signals" and a composite "Variance Score".

### 4.1. Signal Synthesis
| Metric | Threshold | Signal | Recommended Strat |
| :--- | :--- | :--- | :--- |
| **Earnings** | < 5 Days | `EVENT` | Avoid / Speculative |
| **VRP Tactical Markup** | < -10% | `DISCOUNT` | Calendars / Diagonals |
| **Compression** | < 0.75 | `BOUND` | Iron Condors |
| **VRP Tactical Markup** | > +20% | `RICH` | Strangles / Naked Puts |
| **Default** | - | `FAIR` | Pass |

*   **BATS Efficiency (🦇):** A special flag for "Retail Optimal" candidates.
    *   **Criteria:** Price $15-$75 AND `VRP_Structural` > 1.0.
    *   **Goal:** Efficient use of Buying Power for small accounts.

### 4.2. Variance Score (0-100)
A weighted composite score using **Absolute Dislocation**:
*   **Math:** `Score = |VRP - 1.0| * 200`
*   **Logic:** Significant dislocation in **either direction** (Rich or Cheap) resulting in a high score.
*   **Weights:** 50% Structural Dislocation / 50% Tactical Dislocation.
*   **Stability:** VRP Tactical Markup calculation uses a **5.0 HV Floor** and **3.0 Cap** to prevent "Infinity %" markup artifacts on flat tape.
*   **Penalty:** Score halving (-50%) if `HV_Rank < 15` (Short Vol Trap).

---

## 5. Configuration & Files

*   `config/trading_rules.json`: The physics constants (Net Liq, Thresholds, Stress Scenarios).
*   `config/strategies.json`: Strategy metadata (Profit Targets, Gamma Triggers).
*   `config/market_config.json`: Futures multipliers, ETF mappings.
