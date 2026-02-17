# ADR 0013: Compression Ratio Decision Framework (Short Vol Strategy)

**Status:** Accepted
**Date:** 2025-12-31
**Decision Makers:** Product (User), Engineering, Quant Review
**Tags:** #volatility #signal #short-vol

---

## Context

Variance is a short volatility strategy. The system previously relied on binary flags (`is_coiled`, `is_expanding`) derived from the Compression Ratio, which:

- Discarded the continuous value (lossy signal).
- Misaligned with short vol behavior (severe compression is risky, not favorable).

## Decision

Use continuous Compression Ratio (HV30 / HV90) directly across signal, regime, and vote logic.

**Thresholds (short vol orientation):**
- < 0.60: Severe compression, avoid (expansion risk)
- 0.60-0.75: Mild compression, caution
- 0.75-1.15: Normal regime
- 1.15-1.30: Mild expansion, favorable
- > 1.30: Severe expansion, strongest short vol edge

**Composite coiled check:**
To classify as coiled, require BOTH:
- HV30 / HV90 < 0.75 (long-term compression)
- HV20 / HV60 < 0.85 (medium-term compression)

## Consequences

- Signal types now include `COILED-SEVERE`, `COILED-MILD`, `EXPANDING-MILD`, `EXPANDING-SEVERE`.
- Vote logic incorporates compression thresholds (e.g., `AVOID (COILED)` and `STRONG BUY`).
- TUI displays Compression Ratio directly.
- Removes obsolete compression flag thresholds from configuration.

## Rationale

Mean reversion favors contraction when volatility is elevated and expansion when volatility is compressed. For short vol strategies, that implies:

- Low compression ratio is a warning (expansion likely).
- High compression ratio is favorable (contraction likely).

This aligns the score, signal, and vote with the actual risk mechanics of short premium trading.
