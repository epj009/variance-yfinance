# Multi-Tag Triage System

## Overview
Variance uses a **Collector Pattern** for triage. Unlike standard chains that stop at the first match, our chain allows a position to accumulate multiple tags (e.g., `HARVEST` + `EARNINGS_WARNING`).

## Data Structure
Every `TriageResult` contains a `tags` list:

```json
"tags": [
    {"type": "HARVEST", "priority": 10, "logic": "Profit target hit"},
    {"type": "EARNINGS_WARNING", "priority": 70, "logic": "Earnings in 3d"}
]
```

## TUI Visualization
The TUI renders tags as color-coded badges in the row detail:
- **Primary Badge:** The tag with the lowest priority number.
- **Secondary Badges:** Shown in muted brackets (e.g., `[ERN]`).

## Logic Injection
To ensure backward compatibility, the primary badge is automatically injected into the `logic` string field during triage.
