# Proxy Methodology: The Hybrid Signal

## 1. The Challenge: Data Fragmentaton
In retail quantitative trading, many assets (especially Futures and small ETFs) suffer from **Data Blackouts**:
*   **Futures Options:** Yahoo Finance and other free APIs do not provide options chains for futures tickers.
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
