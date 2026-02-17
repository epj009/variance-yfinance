# ADR 0004: Logarithmic VRP Calculation

## Status
**REJECTED** - Not Implemented

## Superseded By
ADR-0012: VRP Measurement Methodology (Linear Ratio Approach)

## Context
Volatility (IV) is not linear. A move from 20 to 30 IV is more significant than a move from 80 to 90. This ADR proposed using logarithmic transformation to normalize VRP across volatility regimes.

## Decision
~~The engine calculates VRP using logarithmic space: `log(IV / HV)`.~~

**RETRACTED:** The system uses **linear ratios** (`IV / HV`) without logarithmic transformation.

## Rationale for Rejection
After implementation and empirical testing, the linear ratio approach proved superior:

1. **Credit Scaling:** Options premium scales proportionally with IV (ratio), not logarithmically
2. **Market Convention:** Industry quotes "IV trading at 1.2x realized" (ratio language)
3. **Empirical Performance:** Linear ratios with proper threshold calibration (ADR-0010) achieve target pass rates without additional transformation
4. **Interpretability:** Ratio is intuitive - "20% markup" is clearer than "log difference of 0.18"

## Implementation Reality
**VRP Structural:** `IV / HV90` (linear ratio)
**VRP Tactical:** `IV / HV30` (linear ratio)

Thresholds are empirically calibrated per ADR-0010 to account for data source characteristics.

## References
- ADR-0012: VRP Measurement Methodology (provides full mathematical justification for linear ratio approach)
- ADR-0010: VRP Threshold Calibration (empirical threshold derivation)
