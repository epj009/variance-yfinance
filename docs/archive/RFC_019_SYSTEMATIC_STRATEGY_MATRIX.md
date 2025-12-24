# RFC 019: Systematic Strategy Matrix

## 1. Objective
Formalize the mapping between identified trade structures and their mechanical implementations to ensure consistent triage across all risk archetypes.

## 2. Strategy Taxonomy
The engine classifies all strategies into four primary "Risk Archetypes."

### 2.1 Short Volatility (Theta Collectors)
*   **Mechanic:** Exploits VRP via time decay. Short Vega.
*   **Strategies:** Short Strangle, Iron Condor, Naked Put, Covered Call, Vertical Credit Spreads.
*   **Implementation:** `ShortThetaStrategy` (Active).

### 2.2 Time Spreads (Theta Collectors / Vega Long)
*   **Mechanic:** Exploits the difference in decay rates between expiries. Long Vega.
*   **Strategies:** Calendar Spreads, Diagonal Spreads, PMCC (Poor Man's Covered Call).
*   **Implementation:** `TimeSpreadStrategy` (Proposed).

### 2.3 Long Volatility (Gamma/Vega Long)
*   **Mechanic:** Exploits realized movement exceeding implied movement.
*   **Strategies:** Long Straddle, Long Strangle, Vertical Debit Spreads.
*   **Implementation:** `LongVolStrategy` (Proposed - currently uses Default).

### 2.4 Multi-Structure (Complex / Skew)
*   **Mechanic:** Exploits vertical or horizontal skew anomalies.
*   **Strategies:** Ratio Spreads, Butterflies, Broken Wing Butterflies, ZEBRA.
*   **Implementation:** `SkewStrategy` (Proposed - currently uses Default).

## 3. The Implementation Matrix

| Strategy ID | Name | Current Implementation | Target Implementation |
| :--- | :--- | :--- | :--- |
| `short_strangle` | Short Strangle | `ShortThetaStrategy` | **Hardened** |
| `iron_condor` | Iron Condor | `ShortThetaStrategy` | **Hardened** |
| `covered_call` | Covered Call | `ShortThetaStrategy` | **Hardened** |
| `call_calendar_spread` | Call Calendar | `DefaultStrategy` | `TimeSpreadStrategy` |
| `put_calendar_spread` | Put Calendar | `DefaultStrategy` | `TimeSpreadStrategy` |
| `call_diagonal_spread` | Call Diagonal | `DefaultStrategy` | `TimeSpreadStrategy` |
| `ratio_spread_call` | Call Ratio | `DefaultStrategy` | `SkewStrategy` |
| `butterfly_call` | Call Butterfly | `DefaultStrategy` | `SkewStrategy` |
| `long_straddle` | Long Straddle | `DefaultStrategy` | `LongVolStrategy` |

## 4. Mechanical Contract (Strategy Pattern)
Every implementation in the matrix must fulfill the following clinical requirements:
1.  **`is_tested()`**: Define the specific price breach points (e.g., for Calendars, this is the short strike).
2.  **`check_harvest()`**: Strategy-specific profit targets (e.g., 25% for Calendars vs 50% for Strangles).
3.  **`check_toxic_theta()`**: Calculate efficiency relative to the specific risk profile.

## 5. Status
**Proposed.** This RFC acts as the roadmap for the next 4 development cycles.
