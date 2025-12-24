# RFC 015: Relative Volume (RVOL) "Conviction" Gate

## 1. Objective
Differentiate between "Thin Noise" (price moves on low liquidity) and "Institutional Re-pricing" (price moves on high conviction) to validate VRP signals.

## 2. Quantitative Context
Retail data often flags a high VRP on a quiet day. If the richness is not accompanied by volume, the signal is fragile. We want to follow the "Institutional Footprint."

## 3. Proposed Mechanics
### 3.1 RVOL Formula
Compare current daily volume against the tactical average:
$$\text{RVOL} = \frac{\text{Volume}_{Today}}{\text{Avg}(\text{Volume}_{20d})}$$

### 3.2 Signal Validation
- **RVOL > 2.0:** High Conviction. The VRP richness is backed by significant capital flow. Increase **Variance Score** by 10%.
- **RVOL < 0.5:** Low Conviction. The re-pricing is occurring on "Thin Air." Decrease **Variance Score** by 20%.

## 4. Architectural Integration
- **Specification:** Implement `RelativeVolumeSpec(Specification)`.
- **Filtering:** Use RVOL as a "Quality Gate" for the top 5 trade recommendations.

## 5. Status
**Proposed (High Integrity).** Relies on standard exchange-reported volume feeds.
