# Multi-Tag TUI Rendering Design

## Overview
This document describes the design implementation for displaying multiple triage tags per position in the terminal UI.

## Implemented Design: Badge Style

```text
┌──────────────────────────────────────────────────────────────┐
│ Symbol  Strategy         DTE   P/L    Tags                   │
├──────────────────────────────────────────────────────────────┤
│ AAPL    Iron Condor       45  $1250  💰 HARVEST | ☢️γ         │
│ TSLA    Short Strangle    12  -$200  🛡️ DEFENSE | 📅ERN      │
└──────────────────────────────────────────────────────────────┘
```

### Color & Icon Mapping
- 💰 **Green:** Actionable Alpha (HARVEST, SCALABLE).
- 🛡️ **Red:** Critical Risk (EXPIRING, DEFENSE, SIZE_THREAT).
- ☢️ **Yellow:** Technical Warning (GAMMA, TOXIC).
- 📅 **Orange/Blue:** Metadata (EARNINGS, HEDGE_CHECK).

### Rendering Logic
1.  **Primary Tag:** First tag in priority list. Rendered with full name and icon.
2.  **Secondary Tags:** Up to 3 additional tags. Rendered as compact [abbreviations].
3.  **Fallback:** ASCII text `[H]`, `[G]`, `[E]` for limited terminals.

## Configuration
Controlled via `config/trading_rules.json` in the `triage_display` section.
