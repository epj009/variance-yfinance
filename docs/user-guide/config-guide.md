# Trading Rules Configuration Guide

**File**: `config/trading_rules.json`
**Version**: 2.0.0
**Last Updated**: 2025-12-25

## Overview

This file controls **all thresholds and rules** for the Variance trading system. Settings are grouped into logical categories for easy navigation.

**Quick Navigation**:
- [Screening: VRP Thresholds](#screening-vrp-thresholds)
- [Screening: Volatility Checks](#screening-volatility-checks)
- [Screening: IV Percentile](#screening-iv-percentile)
- [Screening: Liquidity](#screening-liquidity)
- [Screening: Retail Efficiency](#screening-retail-efficiency)
- [Portfolio: Risk Limits](#portfolio-risk-limits)
- [Portfolio: Position Management](#portfolio-position-management)
- [Triage](#triage-rules)
- [Hedging](#hedging-strategy)
- [Display](#display-settings)

---

## Screening: VRP Thresholds

Controls the core volatility risk premium (VRP) filtering logic.

### `vrp_structural_threshold` (default: `1.10`)
**Purpose**: Minimum VRP (IV/HV90) required for a symbol to pass screening.

**Formula**: `VRP = IV / max(HV90, hv_floor)`

**Values**:
- `1.10` = IV must be 10% higher than HV90 (balanced - current default)
- `1.00` = IV equals HV90 (break-even, very permissive)
- `1.20` = IV must be 20% higher (conservative)

**Impact**:
- **Higher**: Fewer candidates, only trade when IV is significantly elevated
- **Lower**: More candidates, trade when IV is closer to HV

**Related**:
- Filter: `VrpStructuralSpec`
- See: `docs/user-guide/filtering-rules.md#2-vrpstructuralspec`

---

### `vrp_structural_rich_threshold` (default: `1.30`)
**Purpose**: VRP level considered "rich" - triggers additional safety checks.

**Usage**: When VRP > 1.30, `VolatilityTrapSpec` checks if HV Rank is too low.

**Values**:
- `1.30` = IV is 30% higher than HV90 (balanced)
- `1.50` = Very elevated (only extreme situations)
- `1.10` = Same as base threshold (no special handling)

**Impact**: Controls when positional HV Rank check is applied.

**Related**:
- Filter: `VolatilityTrapSpec`
- See: `docs/user-guide/filtering-rules.md#4-volatilitytrapspec`

---

### `vrp_tactical_threshold` (default: `1.15`)
**Purpose**: Minimum VRP for tactical (short-term) signals.

**Difference from Structural**:
- **Structural**: Based on HV90 (quarterly context)
- **Tactical**: Based on HV20 (monthly context)

**Values**:
- `1.15` = Tactical edge must be 15% (current)
- `1.00` = No tactical edge required

**Impact**: Used in scoring and enrichment, not primary filtering.

---

### `hv_floor_percent` (default: `5.0`)
**Purpose**: Minimum volatility floor to prevent low-vol noise.

**Formula**: `VRP = IV / max(HV, 5.0%)`

**Rationale**: If HV < 5%, VRP signals are unreliable (utility stocks, penny stocks).

**Values**:
- `5.0%` = Standard floor (recommended)
- `3.0%` = More permissive (allows lower-vol stocks)
- `7.0%` = More restrictive

**Impact**: Rejects ultra-low volatility symbols.

**Related**:
- Filter: `LowVolTrapSpec`
- See: `docs/user-guide/filtering-rules.md#3-lowvoltrapspec`

---

## Screening: Volatility Checks

Controls whipsaw protection and volatility momentum filtering.

### `hv_rank_trap_threshold` (default: `15.0`)
**Purpose**: Minimum HV Rank (percentile of 1-year range) when VRP is rich.

**Formula**: When `VRP > 1.30`, require `HV Rank >= 15`

**HV Rank Scale**:
- `0` = Lowest HV in past year
- `50` = Middle of range
- `100` = Highest HV in past year

**Values**:
- `15.0` = Reject bottom 15% (current - balanced)
- `25.0` = Reject bottom 25% (more conservative)
- `5.0` = Reject bottom 5% only (permissive)

**Rationale**: Prevents trading when IV is rich but HV is at yearly lows (falling knife).

**Related**:
- Filter: `VolatilityTrapSpec`
- ADR: `ADR-0011` (Volatility Spec Separation)

---

### `volatility_momentum_min_ratio` (default: `0.85`)
**Purpose**: Minimum HV30/HV90 ratio (universal compression check).

**Formula**: `HV30 / HV90 >= 0.85`

**Values**:
- `0.85` = Allow 15% compression (current - balanced)
- `0.90` = Allow 10% compression (conservative)
- `0.80` = Allow 20% compression (permissive)

**Common Scenarios**:
- `1.00` = HV30 equals HV90 (neutral)
- `0.85` = HV30 is 15% below HV90 (moderate decline, OK)
- `0.60` = HV30 is 40% below HV90 (severe collapse, reject)

**Rationale**: Catches volatility compression across ALL VRP levels (complements `hv_rank_trap_threshold`).

**Related**:
- Filter: `VolatilityMomentumSpec`
- ADR: `ADR-0011` (Volatility Spec Separation)
- Added: 2025-12-25 (fills VRP 1.10-1.30 blind spot)

---

### `vol_trap_compression_threshold` (default: `0.70`)
**Purpose**: Legacy parameter for severe compression detection.

**Status**: **DEPRECATED** - Replaced by `volatility_momentum_min_ratio`.

**Note**: Kept for backwards compatibility. Modern filtering uses `volatility_momentum_min_ratio` instead.

---

### `compression_coiled_threshold` (default: `0.75`)
### `compression_expanding_threshold` (default: `1.25`)
**Purpose**: Signal generation for "coiled" (compressed) vs "expanding" vol states.

**Usage**: Enrichment and scoring, not primary filtering.

**Rationale**: Detect when volatility is compressed (potential breakout) or expanding (momentum).

---

## Screening: IV Percentile

### `min_iv_percentile` (default: `20.0`)
**Purpose**: Minimum IV Percentile (rank in 1-year IV range) required.

**Formula**: `IV Percentile >= 20`

**IV Percentile Scale**:
- `0` = Lowest IV in past year
- `50` = Middle of range
- `100` = Highest IV in past year

**Values**:
- `20.0` = Reject bottom 20% (current - balanced)
- `30.0` = Reject bottom 30% (conservative)
- `10.0` = Reject bottom 10% (permissive)

**Rationale**: Even if VRP > 1.10, we want IV to be elevated vs its own history.

**Exemptions**: None. Tastytrade provides IV Percentile for both equities and futures.

**Related**:
- Filter: `IVPercentileSpec`
- Fix: 2025-12-29 (removed incorrect futures exemption - Tastytrade DOES provide IV% for futures)

---

### `tastytrade_iv_percentile_floor` (default: `20.0`)
**Purpose**: Duplicate of `min_iv_percentile` for legacy compatibility.

**Status**: Kept for backwards compatibility.

---

## Screening: Liquidity

### `min_tt_liquidity_rating` (default: `4`)
**Purpose**: Minimum Tastytrade liquidity rating (1-5 scale).

**Scale**:
- `5` = Excellent (tight markets, high volume)
- `4` = Good (current default)
- `3` = Fair
- `2` = Poor
- `1` = Very Poor

**Values**:
- `4` = Only trade good liquidity (recommended)
- `3` = Allow fair liquidity (more permissive)
- `5` = Only excellent liquidity (very restrictive)

**Fallback**: If Tastytrade rating unavailable, uses `min_atm_volume` and `max_slippage_pct`.

**Safety Guard**: Even if rating >= 4, rejects if slippage > 25% (data anomaly protection).

**Related**:
- Filter: `LiquiditySpec`
- Override: `--allow-illiquid` flag

---

### `min_atm_volume` (default: `500`)
**Purpose**: Minimum ATM option volume (fallback when no Tastytrade rating).

**Values**:
- `500` = Standard (current)
- `1000` = Higher liquidity requirement
- `100` = Lower bar (more permissive)

**Related**: Only used when `liquidity_rating` is unavailable.

---

### `min_atm_open_interest` (default: `500`)
**Purpose**: Minimum ATM open interest (informational, not currently used in filtering).

---

### `max_slippage_pct` (default: `0.05`)
**Purpose**: Maximum allowed bid/ask spread as percentage.

**Formula**: `(Ask - Bid) / Mid <= 0.05`

**Values**:
- `0.05` = 5% slippage max (current)
- `0.03` = 3% (tighter, more conservative)
- `0.10` = 10% (looser, more permissive)

**Related**:
- Filter: `LiquiditySpec` (fallback check)
- Filter: `RetailEfficiencySpec` (primary slippage check)

---

### `liquidity_mode` (default: `"volume"`)
**Purpose**: Liquidity check mode.

**Options**:
- `"volume"` = Check ATM volume
- `"rating"` = Prefer Tastytrade rating

**Status**: Currently informational - code prefers Tastytrade rating when available.

---

## Screening: Retail Efficiency

### `retail_min_price` (default: `25.0`)
**Purpose**: Minimum underlying price for retail traders.

**Rationale**: Below $25, strike density is too tight and gamma risk is too high.

**Values**:
- `25.0` = Standard (Tastylive recommendation)
- `15.0` = Lower bar (allows cheaper underlyings)
- `50.0` = Higher bar (only mid/large-cap stocks)

**Impact**: Rejects cheap stocks, penny stocks, and some futures (e.g., /NG at $3.76).

**Related**:
- Filter: `RetailEfficiencySpec`
- See: `docs/user-guide/filtering-rules.md#6-retailefficiencyspec`

---

### `retail_max_slippage` (default: `0.05`)
**Purpose**: Maximum slippage for retail-friendly execution (redundant with `max_slippage_pct`).

**Note**: Same as `max_slippage_pct`. Kept for clarity/separation.

---

## Screening: Quality

### `min_variance_score` (default: `25.0`)
**Purpose**: Minimum composite quality score for candidates.

**Scale**: 0-100, where higher = better edge quality.

**Values**:
- `25.0` = Minimum acceptable (current)
- `40.0` = Higher quality bar
- `10.0` = Very permissive

---

### `vrp_tactical_aggregation_floor` (default: `-0.50`)
### `vrp_tactical_aggregation_ceiling` (default: `1.00`)
**Purpose**: Bounds for VRP tactical aggregation across expirations.

**Usage**: Multi-expiration VRP calculation.

---

### `vrp_tactical_quality_warning_threshold` (default: `1.00`)
**Purpose**: Threshold for VRP tactical quality warnings.

**Usage**: Data quality checks in enrichment step.

---

## Portfolio: Risk Limits

### `net_liquidity` (default: `50000`)
**Purpose**: Account net liquidity for position sizing.

**Usage**: Risk calculations, concentration checks.

**Values**: Your actual account size (in dollars).

---

### `concentration_risk_pct` (default: `0.25`)
**Purpose**: Maximum position size as percentage of net liquidity.

**Formula**: `position_value / net_liquidity <= 0.25`

**Values**:
- `0.25` = 25% max per position (current - balanced)
- `0.15` = 15% (more conservative)
- `0.33` = 33% (more aggressive)

---

### `concentration_limit_pct` (default: `0.05`)
**Purpose**: Warning threshold for position concentration.

**Usage**: Flags positions > 5% for review.

---

### `size_threat_pct` (default: `0.05`)
**Purpose**: Position size that triggers "SIZE_THREAT" tag.

**Usage**: Triage display - warns when position > 5% of portfolio.

---

### `max_strategies_per_symbol` (default: `3`)
**Purpose**: Maximum number of concurrent strategies per underlying.

**Rationale**: Prevents over-concentration in single name.

**Values**:
- `3` = Max 3 strategies (e.g., short put, iron condor, long call)
- `1` = Only one strategy per symbol (very conservative)
- `5` = More permissive

---

### `allow_proxy_stacking` (default: `false`)
**Purpose**: Allow multiple positions in same proxy family (e.g., SPY + /ES).

**Values**:
- `false` = Prevent proxy stacking (recommended)
- `true` = Allow (increases correlation risk)

**Related**: See `FAMILY_MAP` in `config/runtime.json`.

---

## Portfolio: Position Management

### `vrp_scalable_threshold` (default: `1.35`)
**Purpose**: VRP Tactical Markup required to scale existing position.

**Formula**: `vrp_tactical_markup >= 1.35`

**Rationale**: Only add to position if edge has surged significantly.

**Values**:
- `1.35` = Large edge surge required (current - conservative)
- `1.00` = Moderate surge
- `2.00` = Only extreme surges

**Related**:
- Filter: `ScalableGateSpec`
- See: `docs/user-guide/filtering-rules.md#special-filter-holding-filter`

---

### `scalable_divergence_threshold` (default: `1.10`)
**Purpose**: Alternative trigger for scalability (relative divergence).

**Formula**: `(vrp_tactical_markup + 1.0) / vrp_structural >= 1.10`

**Rationale**: Catches cases where tactical VRP diverges from structural.

---

### `dead_money_vrp_structural_threshold` (default: `0.80`)
**Purpose**: VRP below which position is considered "dead money".

**Usage**: Triage tags positions with VRP < 0.80 (IV collapsed).

---

### `dead_money_pl_pct_low` (default: `-0.10`)
### `dead_money_pl_pct_high` (default: `0.10`)
**Purpose**: P&L range for "dead money" detection.

**Usage**: Position between -10% and +10% P&L with low VRP = dead money.

---

## Portfolio: Correlation

### `max_portfolio_correlation` (default: `0.70`)
**Purpose**: Maximum correlation allowed between candidate and existing portfolio.

**Formula**: `correlation(candidate_returns, portfolio_returns) <= 0.70`

**Values**:
- `0.70` = Moderate correlation allowed (current - balanced)
- `0.50` = Low correlation required (more conservative)
- `0.85` = High correlation allowed (more permissive)

**Example**:
- SPY vs QQQ: ~0.95 correlation (would reject if holding SPY)
- SPY vs GLD: ~0.15 correlation (would allow)

**Related**:
- Filter: `CorrelationSpec`
- See: `docs/user-guide/filtering-rules.md#9-correlationspec`

---

### `beta_weighted_symbol` (default: `"SPY"`)
**Purpose**: Reference symbol for beta-weighting portfolio delta.

**Usage**: Portfolio delta calculations use SPY as benchmark.

**Options**: `"SPY"`, `"QQQ"`, `"/ES"`, etc.

---

## Portfolio: Delta Management

### `portfolio_delta_long_threshold` (default: `75`)
**Purpose**: Portfolio delta threshold for "too long" warning.

**Usage**: Triage flags portfolio if total delta > +75.

**Values**:
- `75` = Moderate long exposure allowed
- `50` = More conservative
- `100` = More permissive

---

### `portfolio_delta_short_threshold` (default: `-50`)
**Purpose**: Portfolio delta threshold for "too short" warning.

**Usage**: Triage flags portfolio if total delta < -50.

---

## Triage Rules

### `gamma_dte_threshold` (default: `21`)
**Purpose**: DTE below which gamma risk is flagged.

**Usage**: Positions with DTE < 21 get "GAMMA" tag.

**Rationale**: Short-dated options have high gamma risk (rapid delta changes).

---

### `profit_harvest_pct` (default: `0.50`)
**Purpose**: P&L percentage that triggers "HARVEST" recommendation.

**Formula**: If position P&L >= 50% of max profit, tag for harvest.

**Values**:
- `0.50` = 50% of max profit (Tastylive standard)
- `0.75` = 75% (let winners run longer)
- `0.25` = 25% (take profits earlier)

---

### `earnings_days_threshold` (default: `5`)
**Purpose**: Days until earnings that trigger warning.

**Usage**: Positions with earnings within 5 days get "EARNINGS_WARNING" tag.

---

### `theta_efficiency_low` (default: `0.1`)
### `theta_efficiency_high` (default: `0.5`)
**Purpose**: Theta efficiency range for position quality.

**Formula**: `theta / gamma`

**Usage**: Flags positions with poor theta efficiency.

---

### `friction_horizon_min_theta` (default: `0.01`)
**Purpose**: Minimum theta to justify holding vs transaction costs.

**Rationale**: If theta < $0.01/day, friction costs may exceed edge.

---

## Hedging Strategy

### `hedge_rules.enabled` (default: `true`)
**Purpose**: Enable/disable hedge detection.

---

### `hedge_rules.index_symbols` (default: `["SPY", "QQQ", ...]`)
**Purpose**: List of symbols considered "hedges".

**Usage**: Long puts in these symbols may be flagged as portfolio hedges.

---

### `hedge_rules.qualifying_strategies`
**Purpose**: Strategy types that qualify as hedges.

**Default**: `["Long Put", "Vertical Spread (Put)", "Diagonal Spread (Put)"]`

---

### `hedge_rules.delta_threshold` (default: `-5`)
**Purpose**: Delta threshold for hedge detection.

**Usage**: Position must have delta < -5 to be considered hedge.

---

### `hedge_rules.require_portfolio_long` (default: `true`)
**Purpose**: Only flag as hedge if portfolio is net long.

**Rationale**: Puts only hedge if you have long exposure to hedge.

---

## Data Validation

### `global_staleness_threshold` (default: `0.50`)
**Purpose**: Maximum staleness ratio for market data.

**Usage**: Warns if data > 50% of expected freshness.

---

### `data_integrity_min_theta` (default: `0.50`)
### `data_integrity_min_gamma` (default: `0.001`)
**Purpose**: Minimum Greeks values for data quality check.

**Usage**: Flags positions with suspiciously low Greeks.

---

### `proxy_iv_score_haircut` (default: `0.85`)
**Purpose**: Score penalty for using proxy IV (futures).

**Formula**: `score * 0.85` when IV is proxied.

**Rationale**: Proxy IV is less reliable than direct IV.

---

### `asset_mix_equity_threshold` (default: `0.80`)
**Purpose**: Equity percentage threshold for portfolio classification.

**Usage**: If portfolio > 80% equities, considered "equity-heavy".

---

### `futures_delta_validation.enabled` (default: `true`)
### `futures_delta_validation.min_abs_delta_threshold` (default: `1.0`)
**Purpose**: Validate futures delta calculation.

**Rationale**: Futures delta should be multiplied by contract multiplier. Warns if < 1.0 (suggests raw delta).

---

## Scoring and Signals

### `variance_score_dislocation_multiplier` (default: `200`)
**Purpose**: Multiplier for VRP dislocation in variance score.

**Usage**: `score += vrp_dislocation * 200`

---

### `vrp_tactical_cheap_threshold` (default: `-0.10`)
**Purpose**: VRP level considered "cheap" (IV < HV).

**Usage**: Flags symbols with VRP < -0.10 (potential long vol opportunities).

---

### `bats_efficiency_min_price` (default: `15`)
### `bats_efficiency_max_price` (default: `75`)
### `bats_efficiency_vrp_structural` (default: `1.0`)
**Purpose**: BATS (balanced ATM short) strategy parameters.

**Usage**: Strategy-specific filtering for balanced short straddles/strangles.

---

## Stress Testing

### `stress_scenarios` (default: 7 scenarios)
**Purpose**: Stress test scenarios for portfolio risk analysis.

**Format**:
```json
{"label": "Crash -5%", "move_pct": -0.05, "vol_point_move": 15.0}
```

**Usage**: Portfolio stress testing calculates P&L under each scenario.

---

## Display Settings

### `triage_display.max_secondary_tags` (default: `3`)
**Purpose**: Maximum number of secondary tags to display per position.

---

### `triage_display.use_icons` (default: `true`)
**Purpose**: Show emoji icons in triage tags.

**Values**:
- `true` = Show icons (🛡️, 💰, etc.)
- `false` = Text only

---

### `triage_display.tag_colors`
**Purpose**: Color mapping for triage tags.

**Format**: `{"TAG_NAME": "color style"}`

**Colors**: `bold yellow`, `bold green`, `bold red`, `dim green`, etc.

---

### `triage_display.tag_icons`
**Purpose**: Emoji mapping for triage tags.

**Format**: `{"TAG_NAME": "emoji"}`

**Icons**:
- `EXPIRING`: ⏳
- `HARVEST`: 💰
- `GAMMA`: ☢️
- `TOXIC`: 💀
- etc.

---

## Migration Guide

### From v1.0 (HV252) to v2.0 (HV90)

**Changed Thresholds** (2025-12-25):
```diff
- "vrp_structural_threshold": 0.85
+ "vrp_structural_threshold": 1.10   # +29%

- "vrp_structural_rich_threshold": 0.95
+ "vrp_structural_rich_threshold": 1.30   # +37%

- "vrp_tactical_threshold": 0.90
+ "vrp_tactical_threshold": 1.15   # +28%
```

**New Settings** (2025-12-25):
```json
"volatility_momentum_min_ratio": 0.85  # NEW - universal compression check
```

**Deprecated**:
- `vol_trap_compression_threshold` (use `volatility_momentum_min_ratio`)

---

## Preset Configurations

### Conservative (High Quality, Fewer Candidates)
```json
{
  "vrp_structural_threshold": 1.20,
  "min_iv_percentile": 30.0,
  "volatility_momentum_min_ratio": 0.90,
  "max_portfolio_correlation": 0.60,
  "min_tt_liquidity_rating": 5
}
```

### Aggressive (More Candidates, Lower Bar)
```json
{
  "vrp_structural_threshold": 1.00,
  "min_iv_percentile": 10.0,
  "volatility_momentum_min_ratio": 0.80,
  "max_portfolio_correlation": 0.80,
  "min_tt_liquidity_rating": 3
}
```

### Balanced (Current Default)
```json
{
  "vrp_structural_threshold": 1.10,
  "min_iv_percentile": 20.0,
  "volatility_momentum_min_ratio": 0.85,
  "max_portfolio_correlation": 0.70,
  "min_tt_liquidity_rating": 4
}
```

---

## Troubleshooting

**Problem**: "No candidates passing filters"
**Solutions**:
- Lower `vrp_structural_threshold` to 1.00
- Lower `min_iv_percentile` to 10.0
- Check if market is in low-vol regime

**Problem**: "Too many candidates"
**Solutions**:
- Raise `vrp_structural_threshold` to 1.20
- Raise `min_iv_percentile` to 30.0
- Lower `max_portfolio_correlation` to 0.60

**Problem**: "Futures not showing up"
**Solutions**:
- Check `retail_min_price` (some futures < $25)
- Check VRP (futures often have low VRP)
- Verify not in `--held-symbols` (needs scalable surge)

---

## References

- **Filter Documentation**: `docs/user-guide/filtering-rules.md`
- **ADR-0010**: VRP Threshold Calibration (HV90)
- **ADR-0011**: Volatility Spec Separation
- **Code**: `src/variance/models/market_specs.py`
- **Diagnostic Tool**: `./variance diagnose <symbol>`
