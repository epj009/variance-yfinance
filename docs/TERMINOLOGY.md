# Variance Terminology Guide

**Purpose**: Standardize terminology across code, documentation, and user-facing interfaces.

---

## Core Concepts

### Screening Process

| Term | Usage | Example |
|------|-------|---------|
| **Screening** | The overall process of finding candidates | "Run the screener" |
| **Filter** | A rule that accepts/rejects candidates | "VRP filter", "liquidity filter" |
| **Candidate** | A symbol that passes filters | "10 candidates found" |
| **Pipeline** | The sequential flow of screening steps | "Filter pipeline" |

**❌ Avoid**: "Screen" (as noun), "gate", "check" (unless specific context)

---

### Filters (User-Facing)

| Term | Usage | Example |
|------|-------|---------|
| **Filter** | Primary user-facing term | "The IV Percentile filter rejects..." |
| **Filter Pipeline** | Sequence of filters | "Symbols pass through the filter pipeline" |
| **Filtering Rules** | Configuration for filters | "See filtering rules documentation" |

**Implementation Note**: Filters are implemented as Specifications (see Technical Terms below).

**Examples**:
- ✅ "The VRP filter requires IV > HV"
- ✅ "Filters are applied in sequence"
- ❌ "The VRP gate checks..."
- ❌ "Screening gates are composable"

---

### Technical Implementation

| Term | Usage | Context |
|------|-------|---------|
| **Specification** | Design pattern name | ADRs, architecture docs |
| **Spec** | Shortened form in code | `VrpStructuralSpec`, `LiquiditySpec` |
| **Specification Pattern** | Formal pattern reference | Technical documentation |

**Examples**:
- ✅ Code: `class VrpStructuralSpec(Specification)`
- ✅ ADR: "Using the Specification Pattern for composable filtering"
- ✅ User Doc: "The VRP filter uses a specification pattern internally"

---

## Volatility Terms

### VRP (Volatility Risk Premium)

| Term | Definition | Formula |
|------|------------|---------|
| **VRP** | Volatility Risk Premium | `IV / HV` |
| **VRP Structural** | Long-term VRP | `IV / HV90` |
| **VRP Tactical** | Short-term VRP | `IV / HV20` |
| **VRP Markup** | Tactical vs Structural difference | `VRP Tactical - VRP Structural` |

**❌ Avoid**: "Vol premium", "implied premium", "IV edge" (use VRP consistently)

---

### Historical Volatility (HV)

| Term | Definition | Timeframe |
|------|------------|-----------|
| **HV20** | 20-day historical volatility | ~1 month |
| **HV30** | 30-day historical volatility | ~1.5 months |
| **HV90** | 90-day historical volatility | ~1 quarter |
| **HV252** | 252-day historical volatility | ~1 year |

**Prefer**: Use number suffix (HV90) over descriptive (quarterly HV)

---

### Implied Volatility (IV)

| Term | Definition |
|------|------------|
| **IV** | Implied Volatility |
| **IV Percentile** (or **IVP**) | IV rank in 1-year range (0-100) |
| **IV Rank** | Same as IV Percentile |

**❌ Avoid**: "Implied vol", "IVol" (use IV)

---

### Volatility Metrics

| Term | Definition | Usage |
|------|------------|-------|
| **HV Rank** | HV percentile in 1-year range | Positional context |
| **Compression** | HV declining (HV30 < HV90) | Momentum context |
| **Expansion** | HV rising (HV30 > HV90) | Momentum context |
| **Volatility Trap** | Rich IV + Low HV Rank | Risk scenario |

---

## Position Management

### Position States

| Term | Definition |
|------|------------|
| **Candidate** | Symbol passing filters (not yet held) |
| **Position** | Held strategy on an underlying |
| **Underlying** | The stock/future/ETF (not the option) |
| **Strategy** | The option structure (e.g., "Iron Condor") |

**❌ Avoid**: "Setup" (ambiguous - use "candidate" or "strategy")

---

### Triage Actions

| Term | Definition |
|------|------------|
| **Triage** | Process of reviewing held positions |
| **Action** | Recommended next step (HARVEST, DEFENSE, etc.) |
| **Tag** | Label indicating position state/risk |

**Primary Actions**:
- **HARVEST** = Take profits
- **DEFENSE** = Manage risk
- **ROLL** = Extend duration
- **CLOSE** = Exit position

**❌ Avoid**: "Alert", "signal" (use "action" or "tag")

---

### Scalability

| Term | Definition |
|------|------------|
| **Scalable** | Position where edge has surged (can add) |
| **Scalable Surge** | VRP Tactical Markup >= 1.35 |
| **Held Position** | Existing position in portfolio |

**Usage**:
- ✅ "Position is scalable - VTM = 1.40"
- ❌ "Position is addable"
- ❌ "Position can be sized up"

---

## Configuration

### Config Files

| Term | Usage |
|------|-------|
| **Trading Rules** | `config/trading_rules.json` |
| **Runtime Config** | `config/runtime.json` |
| **Market Config** | Section of runtime config |
| **System Config** | Section of runtime config |

---

### Thresholds

| Term | Preferred | Avoid |
|------|-----------|-------|
| **Threshold** | ✅ `vrp_structural_threshold` | ❌ `vrp_min`, `vrp_cutoff` |
| **Floor** | ✅ `hv_floor_percent` | ❌ `hv_minimum` |
| **Ceiling** | ✅ `aggregation_ceiling` | ❌ `aggregation_max` |

---

## Data Sources

### Providers

| Term | Usage |
|------|-------|
| **Tastytrade** | Primary data provider (volatility metrics) |
| **yfinance** | Fallback provider (price data) |
| **Provider** | Generic term for data source |

**❌ Avoid**: "Tastyworks" (old brand), "Yahoo Finance" (use yfinance)

---

### Data Types

| Term | Definition |
|------|------------|
| **Market Data** | All data for a symbol (price, IV, HV, Greeks) |
| **Option Data** | Specific to options (Greeks, strikes, expirations) |
| **Greeks** | Option sensitivities (delta, gamma, theta, vega) |

---

## Greeks

| Term | Symbol | Definition |
|------|--------|------------|
| **Delta** | Δ | Price sensitivity |
| **Gamma** | Γ | Delta sensitivity |
| **Theta** | Θ | Time decay |
| **Vega** | ν | Volatility sensitivity |

**Prefer**: Use full word (delta), not symbol (Δ)

---

## Asset Classes

| Term | Examples |
|------|----------|
| **Equity** | AAPL, TSLA, NVDA |
| **ETF** | SPY, QQQ, GLD |
| **Future** | /ES, /CL, /GC |
| **Index** | SPX, VIX (cash-settled) |

**Future Symbol Prefix**: Always use `/` (e.g., `/ES` not `ES`)

---

## Correlation

| Term | Definition |
|------|------------|
| **Correlation** (ρ) | Statistical relationship (-1 to +1) |
| **Proxy** | Related symbol for correlation (e.g., SPY for /ES) |
| **Family** | Group of correlated symbols (e.g., SPY family) |

**❌ Avoid**: "Rho" (Greek letter - use "correlation")

---

## Time

| Term | Definition |
|------|------------|
| **DTE** | Days To Expiration |
| **Expiration** | Option expiration date |
| **Tenor** | Time period (e.g., "30-day tenor") |

**Prefer**: DTE over "days until expiration"

---

## Risk Management

| Term | Definition |
|------|------------|
| **Concentration** | Position size as % of portfolio |
| **Correlation** | Statistical relationship between positions |
| **Delta Exposure** | Net directional risk |
| **Beta-Weighted Delta** | Delta normalized to benchmark (SPY) |

---

## Display/UI

| Term | Usage |
|------|-------|
| **TUI** | Terminal User Interface |
| **Vote** | Recommendation (BUY, SELL, HOLD, WATCH) |
| **Tag** | Visual indicator (GAMMA, HARVEST, etc.) |
| **Icon** | Emoji visual (🛡️, 💰, etc.) |

---

## Consistency Checklist

When writing documentation:
- [ ] Use "filter" not "gate" or "screen" (noun)
- [ ] Use "screening" for the process
- [ ] Use "VRP" not "vol premium"
- [ ] Use "IV" not "implied vol"
- [ ] Use "HV90" not "quarterly HV"
- [ ] Use "candidate" not "setup"
- [ ] Use "threshold" not "minimum" or "cutoff"
- [ ] Use futures prefix `/ES` not `ES`
- [ ] Use "Tastytrade" not "Tastyworks"
- [ ] Use "correlation" not "rho" (user-facing)

When writing code:
- [ ] Class names end in `Spec` (e.g., `VrpStructuralSpec`)
- [ ] Inherit from `Specification` base class
- [ ] Method: `is_satisfied_by(metrics)`
- [ ] Compose with `&`, `|`, `~` operators

---

## Version History

- **1.0.0** (2025-12-25): Initial terminology guide
- Standardized "filter" vs "gate" vs "spec" usage
- Clarified VRP, HV, IV terminology
- Defined position management terms
