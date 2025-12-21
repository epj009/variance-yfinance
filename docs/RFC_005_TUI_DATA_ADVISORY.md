# RFC 005: TUI Data Integrity Advisory

| Status | Proposed |
| :--- | :--- |
| **Author** | Variance (Quant Agent) |
| **Date** | 2025-12-21 |
| **Area** | Visualization / Safety |

## 1. Summary
This RFC proposes adding a high-visibility **"DATA ADVISORY"** banner to the top of the Variance TUI. This component will intercept critical data integrity failures—specifically Theta/Gamma unit mismatches (per-share vs. per-contract bugs) and widespread data staleness—that are currently calculated in the analysis engine but hidden from the user in the presentation layer.

## 2. Motivation
The `analyze_portfolio.py` engine currently detects several critical failure modes:
1.  **Unit Mismatches:** When broker CSVs report per-share Greeks instead of position totals, risk metrics (Tail Risk) can be understated by **100x**.
2.  **Stale Data:** When >50% of the portfolio pricing is stale (e.g., weekend/holiday or API failure).
3.  **Liquidity Traps:** When bid/ask spreads widen to "untradeable" levels.

**The Problem:**
While these warnings are written to `variance_analysis.json` (under `data_integrity_warning` and `data_freshness_warning`), the `tui_renderer.py` **does not display them**. A user could be looking at a "Safe" dashboard while their actual tail risk is catastrophic due to a CSV import error.

**The Goal:**
To ensure "Silent Failures" are impossible. If the data is suspect, the dashboard must scream.

## 3. Proposed Design

### 3.1. The Advisory Banner
A conditional `rich.Panel` will be injected at the very top of the dashboard, *before* the Capital Console.

**Style:** `bold white on red` (Critical) or `bold black on yellow` (Warning).

**Trigger Logic:**
The banner appears **IF AND ONLY IF**:
*   `data_integrity_warning['risk']` is `True`.
*   `data_freshness_warning` is `True`.
*   `health_check['liquidity_warnings']` is not empty.

### 3.2. Visual Mockup

**Scenario A: Critical Unit Error (100x Risk Understatement)**
```text
╭───────────────────────────── 🛑 CRITICAL DATA ADVISORY ─────────────────────────────╮
│                                                                                     │
│  ⚠️  INTEGRITY ERROR: Suspicious Theta/Gamma Values Detected                        │
│     Average theta (-0.02) implies PER-SHARE Greeks. Risk metrics are likely         │
│     UNDERSTATED BY 100x. Check your CSV import settings immediately.                │
│                                                                                     │
╰─────────────────────────────────────────────────────────────────────────────────────╯
```

**Scenario B: Stale Data (Weekend/Holiday)**
```text
╭───────────────────────────── ⚠️  DATA FRESHNESS WARNING ────────────────────────────╮
│                                                                                     │
│  🕒  Market data is Stale (>50% of symbols).                                        │
│     P/L and Greeks may not reflect current market conditions.                       │
│                                                                                     │
╰─────────────────────────────────────────────────────────────────────────────────────╯
```

## 4. Implementation Plan

### 4.1. Source Data
The renderer will read from the existing `variance_analysis.json` fields:
*   `data_integrity_warning`: `{ "risk": bool, "details": str }`
*   `data_freshness_warning`: `bool`

### 4.2. Renderer Logic (`tui_renderer.py`)
Add a new method `render_advisory()` called at the start of `render()`.

```python
def render_advisory(self):
    warnings = []
    
    # 1. Integrity Check
    integrity = self.data.get('data_integrity_warning', {})
    if integrity.get('risk'):
        warnings.append(f"[bold]INTEGRITY ERROR:[/bold] {integrity.get('details')}")

    # 2. Freshness Check
    if self.data.get('data_freshness_warning'):
        warnings.append("[bold]STALE DATA:[/bold] >50% of portfolio pricing is outdated.")

    if not warnings:
        return

    # Render Panel
    warning_text = "\n".join(warnings)
    self.console.print(Panel(warning_text, style="bold white on red", title="🛑 CRITICAL ADVISORY"))
```

## 5. Alternatives Considered
*   **Pop-up Dialog:** Too intrusive for a CLI tool; breaks scriptability.
*   **Footer Warning:** Too easily ignored.
*   **Crash/Exit:** Too aggressive; user may still want to see the "best effort" analysis to diagnose the issue.

## 6. Decision
This feature is queued for implementation to close the safety gap between the Engine (Analysis) and the Pilot (User).
