# RFC 011: Relative Value Specifications (The Outlier Signal)

## 1. Objective
Reduce portfolio correlation risk and increase "Precision Alpha" by filtering for idiosyncratic outliers within their respective sectors.

## 2. Quantitative Context
In high-volatility regimes (e.g., a global correction), all assets show high VRP. Selling premium across the board leads to "Correlation Drag." We only want to trade assets that are **Expensive relative to their peers.**

## 3. Proposed Mechanics
### 3.1 Sector Pass
- The `vol_screener.py` will perform a pre-calculation pass on the entire watchlist.
- It will calculate the **Median VRP Structural** for each sector (Metals, Energy, Financials, etc.).

### 3.2 The RV Specification
Implement a new `SectorRelativeSpec` using the Specification Pattern:
- **Condition:** $VRP_{Asset} > (VRP_{SectorMedian} \times 1.25)$
- **Logic:** Only assets that are 25% richer than their sector average will pass.

## 4. Architectural Benefits
- **Modular Filtering:** Leverages the existing `Specification` pattern without altering the core search loop.
- **Dynamic Thresholds:** The "Bar for Richness" automatically rises when the whole market gets expensive, preventing over-allocation during regime shifts.

## 5. Status
**Back-Burner.** Scheduled for future tactical hardening.
