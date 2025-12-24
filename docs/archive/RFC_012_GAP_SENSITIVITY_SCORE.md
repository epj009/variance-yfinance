# RFC 012: Gap Sensitivity Score (Tail Risk Detection)

## 1. Objective
Identify assets with a historical propensity for "Black Swan" gaps (overnight moves that bypass option strikes) to harden the engine against "Hazard Pay" premium.

## 2. Quantitative Context
Assets often show a high VRP not because the premium is "Rich," but because the market is pricing in a known risk of discontinuous price movement (e.g., Clinical Trials, Regulatory Decisions, or thin liquidity in Futures).

## 3. Proposed Mechanics
### 3.1 The "Gap" Metric
We analyze the last 252 trading days of price action:
- **Intraday Kurtosis:** Measure the "fatness" of the tails in log returns.
- **Gap Frequency:** Count instances where $|ln(Open_{today} / Close_{yesterday})| > 2 \times \sigma$.

### 3.2 Scoring
The **Gap Sensitivity Score (0-10)**:
- **0-3 (Stable):** Smooth price discovery. Ideal for naked Strangles.
- **4-7 (Jumpy):** Prone to overnight moves. Favor Defined Risk (Iron Condors).
- **8-10 (Hazardous):** Frequent gaps. Force a `SIZE_THREAT` alert regardless of VRP.

## 4. Triage Integration
- **Constraint:** If Gap Score > 7, the engine will automatically recommend **Defined Risk** strategies only.
- **Alert:** Add `[GAP RISK]` tag to the TUI.

## 5. Status
**Proposed (High Integrity).** Relies strictly on historical closing prices.
