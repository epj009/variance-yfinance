# Variance Quantitative Playbook

This document defines the clinical philosophy and mathematical mechanics of the Variance Engine.

## 1. Core Concepts
The engine operates on the principle that market direction is noise, and volatility is signal.

---

## 2. Volatility Risk Premium (VRP) Mechanics
The engine's primary "Alpha" signal is the **Volatility Risk Premium (VRP)**. This is the statistical edge gained by selling options premium when implied volatility (IV) is significantly higher than realized volatility (HV).

Variance uses **Institutional Grade Decimal Ratios** for all VRP measurements.

### 2.1. VRP (Structural) - The "Fair Value" Baseline
*   **Metric:** `IV30 / HV90` (Institutional)
*   **Function:** Measures the long-term premium markup.
*   **Threshold:** `> 1.0` (Positive VRP).
*   **Significance:** This is the "Strategic Edge." It tells us if an asset is historically overvalued. We use the 90-day realized volatility (Tastytrade Native) as the "denominator of reality."

### 2.2. VRP (Tactical) - The "Immediate Opportunity"
*   **Metric:** `IV30 / HV30` (Institutional)
*   **Function:** Measures current IV against the most recent 30 days of price action.
*   **Threshold:** `> 1.0` (Immediate edge).
*   **Significance:** This is the "Tactical Edge." It identifies assets where the market is panicking (buying insurance) relative to how the stock is *actually* moving right now. 

### 2.3. VRP Divergence (Alpha Momentum)
*   **Formula:** `Divergence = VRP_Tactical / VRP_Structural`
*   **Clinical Goal:** Measures the "Velocity of Edge." 
*   **Signal ↑↑:** Tactical edge is expanding faster than the long-term trend (Surging Alpha).
*   **Signal ↓↓:** Tactical edge is mean-reverting (Decaying Alpha).

### 2.4. Alpha-Theta (Expected Yield)
*   **Concept:** Standard Theta decay is a "Raw" estimate. Alpha-Theta is "Quality-Adjusted" Theta.
*   **Formula:** `Alpha-Theta = Raw Theta * VRP_Ratio`
*   **Significance:** If you have $100 of Theta in a stock where VRP is 1.5, your "Alpha-Theta" is $150. You are being "overpaid" for the time you are holding the risk.

### 2.5. Toxic Theta (The Mechanical Stop)
*   **Formula:** `Efficiency = Abs(Theta) / Expected_Gamma_Cost`
*   **Expected_Gamma_Cost:** `0.5 * Gamma * (Expected_Move^2)`
*   **Significance:** This check (derived from institutional market-making) determines if the "Time Rent" (Theta) you collect is sufficient to pay for the "Movement Insurance" (Gamma) you are providing.
*   **Trigger:** If `Efficiency < 0.10`, the trade is marked `TOXIC`. The cost of movement risk is mathematically higher than the decay you are collecting. Exit immediately.

### 2.6. Why Ratio (Not Spread)?

**Academic VRP:** `VRP = IV - HV` (spread in vol points)
**Our Approach:** `VRP = IV / HV` (ratio, dimensionless)

**Why Ratio is Superior for Retail:**

1. **Credit Scales with Vol**
   - Sell strangle on 20% IV stock → Collect $2.00
   - Sell strangle on 40% IV stock → Collect $4.00
   - Premium doubles when vol doubles → Edge is proportional

2. **Cross-Sectional Comparison**
   - Stock A: IV=12%, HV=10% → Spread=2pts, Ratio=1.20 (20% markup)
   - Stock B: IV=52%, HV=50% → Spread=2pts, Ratio=1.04 (4% markup)
   - Same absolute spread, but Stock A has 5x better relative edge

3. **Risk-Adjusted Edge**
   - Expected move = Price × IV × sqrt(DTE/365)
   - Both risk AND premium scale with vol
   - Edge is the percentage markup, not absolute points

**Academic spread is for variance swaps (institutional). Ratio is for options selling (retail).**

**See:** `docs/adr/0012-vrp-measurement-methodology.md` for full analysis

### 2.7. Why ATM IV (Not OTM)?

**We Measure:** ATM IV (50-delta)
**We Trade:** OTM options (20-30 delta strangles)

**Why ATM is Still Correct:**

1. **ATM Anchors the Entire Surface**
   - All strikes priced relative to ATM: `IV_strike = ATM_IV + Skew`
   - If ATM is rich, wings are also rich
   - Skew (~3-4 pts) is stable; ATM movement drives surface

2. **Skew Cancels for Delta-Neutral**
   ```
   Wing IV = (25d_put_iv + 25d_call_iv) / 2
           = (ATM + 3pts) + (ATM - 2pts) / 2
           = ATM + 0.5pts ≈ ATM
   ```
   Skew effects cancel when averaging both sides

3. **Tastylive/Spina Methodology**
   - Mechanical strike selection (always 20-30 delta)
   - No skew optimization
   - Focus on overall IV vs HV

**For delta-neutral strategies, ATM is the best proxy. Measuring wings gives nearly identical result.**

**See:** `docs/adr/0012-vrp-measurement-methodology.md` for proof

---

## 3. Regime Detection
Variance separates **Valuation** (is it expensive?) from **Regime** (is it about to move?).

### Coiled (🌀)
*   **Metric:** `HV30 / HV90 < 0.75`.
*   **Meaning:** Realized volatility is significantly lower than its medium-term trend. Like a compressed spring, energy is being stored.
*   **Risk:** Higher probability of a violent breakout. Range-bound trades (Iron Condors) are dangerous here.

### Expanding (⚡)
*   **Metric:** `HV30 / HV90 > 1.25`.
*   **Meaning:** The asset is currently moving 25% more than its quarterly average.
*   **Trading:** Favor trend-following or respect the momentum. Mean reversion (short vol) may be "steamrolled" by the trend.

---

## 4. The Hard Gates (Institutional Safety)

### 4.1. The North Star Gate
*   **Mechanism:** If the "North Star" (SPY) data cannot be reached or is invalid, the engine aborts the entire run.
*   **Why:** Without SPY, beta-weighting and probabilistic stress tests are meaningless.

### 4.2. The Volatility Trap Gate
*   **Mechanism:** Dual-trigger rejection of "Rich" setups that are artifacts of dead realized movement.
*   **Trigger 1 (Positional):** `HV Rank < 15` (Today's movement is at a 1-year low).
*   **Trigger 2 (Relative):** `HV30 / HV90 < 0.70` (Today's movement is 30% below its quarterly trend).

### 4.3. The Retail Efficiency Gate
*   **Mechanism:** Habit-enforcing filter to ensure trades are mechanically manageable for retail accounts.
*   **Price Floor:** Reject underlyings `< $25.00` (prevents explosive Gamma and poor strike density).
*   **Slippage Guard:** Reject options with Bid/Ask spreads `> 5%` of price.

---

## 5. Scoring (The Variance Score)
The Variance Score (0-100) is a composite measure of institutional opportunity:
*   **Structural VRP:** Long-term valuation edge (dislocation from fair value).
*   **Tactical VRP:** Immediate timing edge (dislocation from fair value).
*   **Volatility Momentum:** HV30/HV90 confirmation (trend vs compression).
*   **HV Rank (Rich Only):** Avoid positional traps when VRP is rich.
*   **IV Percentile:** Statistical extreme context.
*   **Yield:** Normalized premium yield (30-day basis).
*   **Retail Efficiency:** Price + slippage viability.
*   **Liquidity:** Rating/volume/spread quality.

**Note:** Component weights and ceilings are configurable in `config/trading_rules.json`
(`variance_score_weights` and `variance_score_*_ceiling`).

---

## 6. Allocation Vote
The engine provides a definitive clinical "Vote" for every candidate:
*   **BUY:** High Score (>70) and Low Portfolio Correlation (Rho < 0.50).
*   **SCALE:** Already held, but VRP is surging (Divergence > 1.10).
*   **LEAN:** High Score but moderate correlation (Rho < 0.65).
*   **HOLD:** Already held, maintaining status quo.
*   **AVOID:** Extreme correlation risk (Rho > 0.70) or mechanical inefficiency.

---

## 7. Mechanical Management (The Strategy Matrix)
Variance applies specific clinical management rules based on the strategy archetype (RFC 019).

### 7.1. Profit Harvesting Targets
*   **Standard Short Vol (50%):** Strangles, Iron Condors, Covered Calls. Edge is high, but we exit at 50% to maximize the "Law of Large Numbers."
*   **Complex Spreads (25%):** Calendars, Diagonals, Butterflies. These have more horizontal/skew risk; we take profit earlier to avoid the "Pin Trap."

### 7.2. Defensive Thresholds
*   **The Gamma Zone (21 DTE):** All premium selling positions are marked `[GAMMA]` when within 21 days of expiration.
*   **Breach Detection:** A position is marked `[DEFENSE]` if the underlying price penetrates the short strike AND it is within the Gamma Zone.

---

## 7. The Quantitative Standard: Logarithmic Space

Variance operates in **Logarithmic Space** rather than **Arithmetic Space**. This is the standard used by institutional quant firms and market makers to maintain mathematical objectivity across different price and volatility scales.

### 7.1. Why Log-Ratios?
In retail trading, users often subtract volatility (e.g., $IV - HV = 5\%$). Variance rejects this because it lacks **Scale Symmetry**.

1.  **Scale Fairness:** A 5-point "spread" on a 15% HV asset is a **33% markup**. A 5-point spread on a 95% HV asset is only a **5% markup**. Log-ratios ensure we only trade when we are being paid a significant *multiple* of the risk.
2.  **Symmetry of Movement:** In regular math, an asset doubling (+100%) and an asset being cut in half (-50%) look like different magnitudes. In **Log Space**, they are the exact same distance from the mean, allowing our risk models to treat upside and downside "tails" with equal mathematical weight.
3.  **Fat Tails & Mean Reversion:** By treating VRP as a ratio ($IV / HV$), we can calculate exactly how many **units of historical movement** the current price covers. This is the foundation of the **Variance Score**—it identifies statistical dislocations that are objectively "too far" from the historical average.

### 7.2. Stoic Quant Philosophy
*   **We do not trade "stories"; we trade mispriced distributions.**
*   **Subtraction is noise; Division is signal.**
*   **If the ratio isn't rich, the trade doesn't exist.**
# Proxy Methodology: The Hybrid Signal

## 1. The Challenge: Data Fragmentaton
In retail quantitative trading, many assets (especially Futures and small ETFs) suffer from **Data Blackouts**:
*   **Futures Options:** legacy data source and other free APIs do not provide options chains for futures tickers.
*   **Thin ETFs:** Tickers like `FXC` (CAD) or `SHY` (2Y Bond) often have "dead" options markets with 0.0 bids and near-zero open interest, making their Implied Volatility (IV) unreadable.

## 2. The Solution: Idiosyncratic Hybrid Signals
Variance uses a **Hybrid Signal** approach to ensure continuous mechanical oversight without sacrificing asset-specific personality.

### The Equation
$$VRP = \frac{IV_{Benchmark}}{HV_{Asset}}$$

1.  **IV Numerator (The Environment):** We use a **Liquid Category Benchmark** (e.g., `FXE` for all Currencies, `IEF` for all Interest Rates). These benchmarks reflect the broad "Cost of Insurance" for that asset class. Because they are highly liquid, they provide a reliable, real-time volatility signal.
2.  **HV Denominator (The Reality):** We use the **Actual Asset's Price Action** (e.g., `/6C` Loonie movement). This preserves the idiosyncrasy of the specific trade.

### Why This Works
If the Canadian Dollar is quiet (5% HV) but the global currency environment is expensive (10% IV via `FXE`), Variance will correctly identify the Loonie as **2x RICH**. Even though it shares an IV numerator with the Euro, its unique denominator forces a unique signal.

## 3. Current Proxy Mappings

| Future | Proxy IV Source | Methodology |
| :--- | :--- | :--- |
| **Loonie (/6C)** | `FXE` (Euro) | Currency Correlation |
| **Aussie (/6A)** | `FXE` (Euro) | Currency Correlation |
| **2Y Bond (/ZT)** | `IEF` (7-10Y Bond) | Rate Curve Correlation |
| **Nasdaq (/NQ)** | `^VIX` (SP500) | Equity Correlation |
| **Oil (/CL)** | `USO` (Oil ETF) | Direct Proxy |
| **Gold (/GC)** | `GLD` (Gold ETF) | Direct Proxy |

## 4. Risks & Considerations
*   **Basis Risk:** There is a minor risk that a specific asset (e.g., CAD) decouples from its category benchmark (e.g., EUR). 
*   **Skew Inaccuracy:** Benchmarks do not capture the specific vertical or horizontal skew of the idiosyncratic asset.
*   **Dashboard Labeling:** Always check the `Proxy` label on the dashboard (e.g., "IV via FXE") to know which benchmark is currently driving the richness signal.
# The Strategy Playbook (Management & Defense)

This document defines the mechanical rules for managing, defending, and closing specific option strategies. The Agent (**Variance**) must refer to this file when a strategy is identified in the portfolio to determine the correct course of action.

### 1. Short Strangle (Undefined Risk)
* **Bias:** Neutral (can be Skewed Bullish/Bearish).
* **Setup:** Sell ~16-20 Delta Call and ~16-20 Delta Put.
* **Target:** 50% Profit.
* **Defense (Tested):**
    * Roll the *untested* side closer (e.g., if Put is ITM, roll Call down to 30 Delta).
    * If < 21 DTE, roll *both* legs out in time (for a credit).
    * *Warning:* If Inverted, look to close for a scratch or small loss.
* **Stop:** 2x the Initial Credit Received.

### 2. Iron Condor (Defined Risk)
* **Bias:** Neutral (can be Skewed Bullish/Bearish).
* **Setup:** Sell ~20 Delta Strangle, Buy ~5-10 Delta Wings.
* **Target:** 50% Profit.
* **Defense (Tested):**
    * Roll the *untested* spread closer (turn it into an Iron Fly or narrower Condor).
    * *Warning:* Do not roll Iron Condors out in time unless you can get a significant credit (> 10% of width). Usually better to close or hold.
* **Stop:** Max Loss (defined).

### 3. Iron Butterfly (Defined Risk)
* **Bias:** Neutral.
* **Setup:** Sell ATM Call & Put, Buy Wings (Width determines risk).
* **Target:** 25% Profit (due to lower probability).
* **Defense (Tested):**
    * Do not roll the tested side.
    * Roll the *untested* wing closer to reduce risk, but this locks in a loss.
    * Generally, hold through expiration or close at stop.
* **Stop:** Max Loss (defined).

### 4. Jade Lizard (Bullish/Neutral)
* **Bias:** Bullish (Positive Delta).
* **Setup:** Sell Short Put + Sell Call Credit Spread. Net Credit > Width of Call Spread.
* **Target:** 50% Profit.
* **Defense:**
    * *Downside (Put ITM):* Manage like a Naked Put. Roll out in time or roll Call Spread down.
    * *Upside (Call ITM):* Do nothing. You have no risk to the upside if set up correctly.

### 5. Twisted Sister (Bearish/Neutral)
* **Bias:** Bearish (Negative Delta).
* **Setup:** Sell Short Call + Sell Put Credit Spread (Inverse Jade Lizard).
* **Target:** 50% Profit.
* **Defense:**
    * *Upside (Call ITM):* Manage like a Naked Call. Roll out in time or roll Put Spread up.
    * *Downside (Put ITM):* Do nothing (No risk if Credit > Width).

### 6. Vertical Spread (Defined Risk)
* **Bias:** Directional (Bullish: Short Put/Long Call; Bearish: Short Call/Long Put).
* **Setup:** Buy one, Sell one (same type).
* **Target:** 50% Profit.
* **Defense:** Generally, **do nothing**. Defined risk trades are binary probabilities.
    * *Exception:* If implied volatility crushes and price is near strikes, you *might* roll out for a credit, but it's rare.

### 7. Ratio Spread (Undefined Risk)
* **Bias:** Directional (Bullish: Put Ratio; Bearish: Call Ratio).
* **Setup:** Buy 1 ATM Option, Sell 2 OTM Options (same type).
* **Target:** 25-50% Profit.
* **Defense:**
    * *Tested (Short Strikes):* Massive risk. Roll the naked short unit out in time or close the whole trade.
    * *Tested (Long Strike):* This is the "sweet spot." Hold or take profit.

### 7b. Broken Wing Butterfly (Defined/Skewed Risk)
* **Bias:** Directional (Bullish: Put BWB; Bearish: Call BWB).
* **Setup:** Traditional butterfly with one wing wider to reduce/offset the debit (ideally for a small credit).
* **Target:** 25-50% Profit.
* **Defense:** Defined risk; usually do nothing. If tested and near max loss, close or roll the tested short strike out in time for a credit if available.

### 8. Calendar / Diagonal Spread (Time Spread)
* **Bias:** Neutral (Calendar) or Directional (Diagonal).
* **Setup:** Short Front Month, Long Back Month.
* **Target:** 25% Profit (Debit trade).
* **Defense:**
    * If the Short Front Month goes ITM: Roll it out to the next week/month to reduce cost basis.
    * *Goal:* Reduce the debit paid to zero (Free trade).

### 9. Covered Call (Bullish)
* **Bias:** Bullish (Positive Delta).
* **Setup:** Long Stock + Short OTM Call.
* **Target:** Campaign mode (Reduce cost basis).
* **Defense:**
    * *Call ITM:* Roll the Call **up and out** (higher strike, later date) for a Net Credit.
    * *Stock Drops:* Roll the Call **down** to generate more credit (reduce basis), but be careful of locking in a loss on the stock rebound.

### 10. Long Options (Speculative)
* **Bias:** Directional (Bullish: Call; Bearish: Put).
* **Setup:** Buy Call or Put.
* **Target:** 50% Profit.
* **Defense:** None. Defined Risk.
* **Stop:** 50% Loss. (Do not hold to zero).

### 11. Naked Short Call / Naked Short Put (Undefined Risk)
* **Bias:** Directional (Bullish: Short Put; Bearish: Short Call).
* **Setup:** Sell OTM call or put. Sized for buying power and risk tolerance.
* **Target:** 50% Profit.
* **Defense:**
    * *Tested & <21 DTE:* Roll out in time for a credit. For calls, consider rolling up/out; for puts, roll down/out.
    * *Deep tested / cannot roll for credit:* Close or convert to defined risk (buy a wing) to cap loss.
    * *Stop:* 2x the Initial Credit Received. (Do not dig the hole deeper).

### 12. ZEBRA (Zero Extrinsic Back Ratio)
* **Bias:** Directional (Bullish: Call ZEBRA; Bearish: Put ZEBRA).
* **Setup:** Buy 2 ITM options, sell 1 ATM/near-ATM option (same type/expiry) to create a ~1:1 stock proxy with minimal extrinsic.
* **Target:** 25-50% Profit or directional move similar to stock.
* **Defense:** Defined risk to near zero; typically do nothing. If badly tested and P/L deteriorates, close or roll the entire structure out in time for a credit if available.
