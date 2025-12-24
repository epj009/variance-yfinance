# ADR 0007: Proxy IV for Futures Screening

## Status
Accepted

## Context
We screen futures but Yahoo Finance does not provide reliable futures options IV for most contracts (e.g., 6A=F, CL=F). Without an IV source, VRP metrics cannot be computed and futures get dropped. Using ETF proxies for *all* math keeps ratios consistent but shifts HV/returns off the traded instrument.

## Decision
- Use bifurcated futures math: futures HV/returns/correlation, proxy ETF IV.
- Do not display a proxy tag in the UI.
- Apply a score haircut to proxy-IV futures (`proxy_iv_score_haircut = 0.85`) to reduce ranking bias without hard gating.

## Alternatives Considered (Not Selected)
- **Proxy-all math (Option 1):** Use proxy ETF for IV/HV/returns. Rejected because it shifts realized volatility off the traded futures.
- **Futures-first with proxy fallback (Option 2):** Equivalent to Option 1 with yfinance data, since futures IV is unavailable.
- **VRP discount (10%) or threshold bump (+0.10):** Both remove marginal futures like `/CL` and `/6J` in current runs; rejected to avoid hard gating.
- **No penalty:** Rejected to avoid over-ranking proxy-IV futures when the ratio is cross-asset.

## Consequences
- **Pros:** Keeps futures HV aligned to the traded instrument while retaining IV for VRP. Avoids missing viable futures opportunities due to absent IV data.
- **Cons:** VRP becomes a cross-asset ratio (futures HV vs ETF IV), which can distort scores during session gaps, roll effects, or tracking error. Lack of UI tagging reduces transparency; the score penalty is a heuristic.
