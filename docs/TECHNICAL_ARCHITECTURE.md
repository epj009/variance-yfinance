# Variance Engine: Technical Architecture

> **Version:** 2.0.0
> **Date:** December 2025
> **Status:** Production-Ready (Core Pipeline) / Active Development (Strategy Engine)

This document provides a comprehensive technical overview of the **Variance Systematic Volatility Engine**. It details the internal logic, mathematical models, and data pipeline architecture for developers and quantitative analysts.

---

## 1. System Design Pattern: The "Data Pipeline"

Variance has evolved beyond a traditional MVC pattern into a **Unidirectional Data Pipeline**. This architecture ensures data consistency, simplifies debugging, and allows for asynchronous processing steps.

**The Pipeline Flow:**
1.  **Ingest (Source of Truth):** `get_market_data.py` pulls raw data from external APIs (yfinance).
2.  **Process (Transformation):** `analyze_portfolio.py`, `triage_engine.py`, and `vol_screener.py` apply business logic, calculating Greeks, VRP, and risk metrics.
3.  **Store (State Persistence):** The processed state is serialized to JSON artifacts (`reports/variance_analysis.json`, `reports/screener_output.json`). This file system acts as the "Database."
4.  **View (Presentation):** `tui_renderer.py` reads the JSON artifacts and renders the Terminal User Interface. It is a "dumb" viewer with no internal logic.
5.  **Act (Agent/Advisor):** The AI Agent (Gemini/Claude) and future Allocator scripts interpret the Store to suggest actions.

---

## 2. Layer 1: The Data Layer (`get_market_data.py`)

The data pipeline is designed for **Resilience** and **Speed**. It does not rely on real-time sockets but uses a high-performance polling architecture with intelligent caching.

### 2.1. Optimized SQLite Cache
*   **Technology:** SQLite in **WAL (Write-Ahead Logging)** mode.
*   **Concurrency:** Thread-local connections allow multi-threaded fetching without locking issues.
*   **Persistence:** Data persists across sessions in `.market_cache.db`.

### 2.2. Resilience Strategies
1.  **Dynamic TTL (Time-To-Live):**
    *   *Market Hours (09:30-16:00):* Short TTL (10-15 mins) for freshness.
    *   *After Hours (16:00-09:30):* TTL extends automatically to **10:00 AM next day**. This bridges the overnight gap where Option Chains are unavailable.
2.  **Partial Data Mode:**
    *   If `yfinance` returns `Price` and `History` (HV) but fails to return `Option Chain` (IV).
    *   **Action:** Returns a "Partial" record (`vrp_structural` = 0.0).
    *   **Impact:** Position P/L/Delta are valid; Volatility metrics suppressed; Screener filters reject symbol.

---

## 3. Layer 2: The Quantitative Engine (`triage_engine.py`)

This module applies the "Physics" of the Variance philosophy to raw positions.

### 3.1. VRP Markup (Alpha-Theta)
We quantify the "Quality of Income" by adjusting raw time decay for the Volatility Risk Premium (VRP).

$$ 	ext{AlphaTheta} = 	ext{Theta}_{	ext{Raw}} 	imes \left( \frac{\text{IV}_{\text{30}}}{\text{HV}_{\text{252}}} \right) $$

*   **Logic:** If IV (20%) > HV (15%), every $1.00 of Theta is statistically "worth" $1.33.
*   **Toxic Theta:** If IV < HV, multiplier < 1.0 -> `TOXIC` flag.

### 3.2. Dynamic Tail Risk
The engine calculates "Max Drawdown" based on the worst outcome of configured stress scenarios.

1.  **Ingest:** Load scenarios (e.g., "-5% Crash") from `config/trading_rules.json`.
2.  **Simulate:** Calculate Portfolio P/L using Delta/Gamma/Vega sensitivities.
3.  **Status:** `Safe` (< 5% Net Liq), `Loaded` (5-15%), `Extreme` (> 15%).

### 3.3. Triage Hierarchy
Action codes assigned via priority waterfall:
1.  **HARVEST:** Profit Target Hit OR Velocity Win.
2.  **SIZE_THREAT:** Tail Risk > 5% Net Liq.
3.  **DEFENSE:** Tested (ITM) + < 21 DTE.
4.  **TOXIC:** VRP < 0.8 + Dead Money.

---

## 4. Layer 3: The Screener (`vol_screener.py`)

Synthesizes raw metrics into actionable "Signals."

### 4.1. Signal Synthesis
| Metric | Signal | Recommended Strat (General) |
| :--- | :--- | :--- |
| **VRP Tactical** > +20% | `RICH` | Sell Premium (Strangle, Lizard) |
| **Compression** < 0.75 | `BOUND` | Iron Condor |
| **VRP Tactical** < -10% | `DISCOUNT` | Calendars / Diagonals |
| **Earnings** < 5 Days | `EVENT` | Avoid / Speculative |

---

## 5. Layer 4: The Strategy Allocator (Future/RFC 007)

*Current Status: In Design (RFC 007)*

This layer will transform the system from a "Screener" to a "Trading Desk" by systematically mapping Opportunities to Mechanics.

### 5.1. The Validator (`mechanics.py`)
A physics engine that validates trade feasibility before recommendation.
*   **Input:** Symbol, Strategy (e.g., Jade Lizard).
*   **Check:** `Credit > Width` (Lizard Rule), `Liquidity Check`.
*   **Output:** `PASS/FAIL`. *Prevents suggesting Lizards on $50 stocks.*

### 5.2. The Allocator (`strategy_allocator.py`)
Maps Market Archetypes to Strategy Menus.
*   **Archetype A (Grinder):** Rich/Normal -> Iron Condor, Strangle.
*   **Archetype B (Spring):** Rich/Coiled -> Jade Lizard, BWB.
*   **Archetype C (Directional):** Skewed -> Ratio Spreads, ZEBRA.
*   **Archetype D (Hedge):** Cheap -> Calendars.

---

## 6. Configuration & Files

*   `config/trading_rules.json`: Physics constants (Net Liq, Thresholds).
*   `config/strategies.json`: Strategy metadata (Profit Targets, Mechanics).
*   `config/market_config.json`: Futures multipliers, ETF mappings.
