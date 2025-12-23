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

## 3. Layer 2: The Strategy Engine (`strategies/`)

Variance uses a **Strategy Pattern** to decouple trade management logic from the data pipeline. This allows for specialized handling of different risk archetypes.

### 3.1. Strategy Hierarchy
- **BaseStrategy:** Abstract interface defining profit harvesting and defense contracts.
- **ShortThetaStrategy:** Specialized for premium sellers (Strangles, Condors). Implements the **Institutional Toxic Theta** filter.
- **DefaultStrategy:** Fallback for unmapped or generic "Custom/Combo" positions.

### 3.2. Quantitative Standard: Logarithmic Space
Variance operates in **Logarithmic Space** to ensure mathematical objectivity across different asset scales.

- **VRP Normalization:** Instead of subtraction ($IV - HV$), we use logarithmic ratios: $ln(IV / HV)$.
- **Scale Symmetry:** Ensures a 1-point move in a low-vol asset (SPY) has the same mathematical weight as a relative move in a high-vol asset.
- **Alpha-Theta:** Quality-adjusted income calculation:
  $$ \text{AlphaTheta} = \text{Theta}_{\text{Raw}} \times \left( \frac{\text{IV}_{\text{30}}}{\text{HV}_{\text{252}}} \right) $$

---

## 4. Layer 3: Domain Model Layer (`models/`)

Logic is encapsulated in robust, typed **Domain Objects** rather than raw dictionaries.

### 4.1. Core Models
- **Position:** Represents a single leg (Option or Stock). Validates raw broker data.
- **StrategyCluster:** Groups legs into a logical strategy. Calculates aggregate Greeks (Net Delta, Theta).
- **Portfolio:** The root object. Manages account-level state, Net Liquidity, and total risk.

---

## 5. Layer 4: The Screener (`vol_screener.py`)

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
*   `config/runtime_config.json` (`market`): Futures multipliers, ETF mappings.
