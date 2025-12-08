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
