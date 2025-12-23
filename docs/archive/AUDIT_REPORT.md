# Audit Report

Target user: retail quant trader using tastylive mechanics; focus is on tradeable signal accuracy and portfolio triage integrity.

## Data Access (market data + CSV parsing)
- Fixed: Liquidity gating now captures Open Interest (OI) and supports `open_interest` mode (RFC 004) to resolve after-hours volume zeroing. `scripts/get_market_data.py:616` `scripts/vol_screener.py:93`
- Medium: IV sampling is ATM by strike distance, not delta-targeted; this can drift from tastylive-style 30-delta/45-DTE mechanics for VRP/edge calculations. `scripts/get_market_data.py:554` `scripts/get_market_data.py:569`
- Fixed: Futures root parsing now preserves micro futures (e.g., /MES, /MNQ, /M2K, /SR3) and avoids truncation. `scripts/portfolio_parser.py:191`
- Medium: `parse_currency` does not handle parentheses negatives (e.g., "(123.45)"), so P/L or cost can parse to 0. `scripts/portfolio_parser.py:141`
- Low: `parse_dte` only strips lowercase "d"; inputs like "45D" or "45 DTE" parse as 0. `scripts/portfolio_parser.py:162`

## Domain Logic (strategy detection + triage)
- High: Triage DTE is derived solely from the `DTE` column, with no fallback to `Exp Date`; missing DTE becomes 0 and can trigger EXPIRING/GAMMA/DEFENSE prematurely. `scripts/triage_engine.py:293` `scripts/triage_engine.py:411`
- High: Concentration/stacking uses `Cost` as exposure; for undefined-risk credit trades, `Cost` is not buying power, so risk concentration is understated and tradeable flags can be too permissive. `scripts/triage_engine.py:779` `scripts/triage_engine.py:793`
- Medium: Strategy clustering groups by `Open Date`; if the field is missing, unrelated legs in the same expiration are merged, causing misclassification (e.g., multiple strangles). `scripts/strategy_detector.py:442` `scripts/strategy_detector.py:474`
- Medium: PMCC/PMCP detection enforces long-leg DTE but does not enforce short-leg DTE or delta windows; diagonals outside tastylive mechanics can be labeled PMCC/PMCP. `scripts/strategy_detector.py:56` `scripts/strategy_detector.py:76`
- Low: Days-held parsing ignores numeric "Days Open" values without a "d" suffix, which can suppress velocity harvest triggers. `scripts/triage_engine.py:238`
- Low: Delta aggregation relies only on `beta_delta`; if missing, delta becomes 0 with no warning, affecting size/hedge logic. `scripts/triage_engine.py:331`

## Screener Layer (signal synthesis + filters + ranking)
- High: Signal type ignores structural VRP flags; high structural VRP can still be labeled `FAIR` when HV20/NVRP is missing or flat, which diverges from tastylive bias mechanics. `scripts/vol_screener.py:115` `scripts/vol_screener.py:134`
- Fixed: Liquidity filter now supports Open Interest (OI) mode (RFC 004), resolving false rejections during after-hours/low-volume windows. `scripts/vol_screener.py:93` `scripts/get_market_data.py:616`
- Medium: `_calculate_variance_score` takes a `rules` arg but uses global `RULES`, so profile overrides do not apply to scoring. `scripts/vol_screener.py:193`
- Medium: Sorting treats `NVRP=0.0` as missing because of `or -9.9`, pushing neutral names to the bottom. `scripts/vol_screener.py:454`
- Medium: Data quality warnings and `is_data_lean` are not used in gating or ranking, so partial/stale data can still be promoted. `scripts/vol_screener.py:369` `scripts/vol_screener.py:436` `scripts/get_market_data.py:743`
- Fixed: Removed unused low-rank summary counter from the screener to avoid misleading metrics. `scripts/vol_screener.py:464`

## Orchestration + Presentation (report assembly + TUI)
- High: Triage `data_quality_warning` is computed but never included in the report payload; the TUI checks for it and silently shows no warning, masking bad data. `scripts/analyze_portfolio.py:131` `scripts/tui_renderer.py:201`
- Medium: `data_freshness_warning` and `data_integrity_warning` are computed but never rendered in the TUI, so users may rely on stale or unit-broken data. `scripts/analyze_portfolio.py:102` `scripts/analyze_portfolio.py:118`
- Medium: BP usage is derived from `total_capital_at_risk` (sum of absolute `Cost`), which is not buying power for undefined-risk credit trades; the display can understate risk. `scripts/analyze_portfolio.py:165` `scripts/analyze_portfolio.py:636`
- Medium: Vol screener table labels `NVRP` as "VRP (T)", which is a markup (%) not a ratio; this can confuse tastylive-oriented users. `scripts/tui_renderer.py:371` `scripts/tui_renderer.py:377` `scripts/vol_screener.py:423`
- Low: `health_check.liquidity_warnings` exists in the report schema but is never populated or rendered. `scripts/analyze_portfolio.py:126`

## Config + Tests (rules consistency + coverage gaps)
- High: Micro futures appear in `FAMILY_MAP` and multipliers but are missing in `SYMBOL_MAP`, so market data fetches for /MES, /MNQ, /M2K, /MGC will fail or proxy incorrectly. `config/runtime_config.json`
- Medium: `FUTURES_PROXY` contains `hv_only` entries that are never handled in the proxy fetcher, so config implies support that does not exist. `config/runtime_config.json` `scripts/get_market_data.py:635`
- Medium: Portfolio delta thresholds exist in config but are not consumed anywhere, which creates false confidence in tuning. `config/trading_rules.json:15`
- Low: Parser tests do not cover uppercase/variant DTE formats or parentheses negatives; current gaps allow regressions in tastylive CSV parsing. `tests/test_portfolio_parser.py:37`

## Cross-Module Risk Summary (tastylive tradeability)
- Highest risk to tradeable accuracy: DTE fallback missing in triage (false EXPIRING/GAMMA) and concentration/BP based on `Cost` rather than buying power.
- Secondary risk: PMCC/PMCP classification lacks short-leg DTE/delta constraints, and data quality warnings are computed but not surfaced to the user.
- Operational risk: micro futures config gaps and proxy types not supported cause silent data failures for popular retail instruments.

## Prioritized Remediation List
- 1) Fix triage DTE fallback to `Exp Date` when `DTE` missing; add tests for uppercase/variant DTE formats.
- 2) Completed: Replace ATM volume filter with OI-first or OI+volume per-leg checks (RFC 004).
- 3) Replace `Cost`-based exposure with BPR/maintenance margin proxy for credit trades; align BP usage and concentration with tasty mechanics.
- 4) Surface `data_freshness_warning`, `data_integrity_warning`, and per-position `data_quality_warning` in the TUI and JSON outputs.
- 5) Enforce PMCC/PMCP short-leg DTE window (e.g., 30-60) and delta window to match tastylive mechanics.
- 6) Add micro futures to `SYMBOL_MAP`/`FUTURES_PROXY`, or explicitly exclude them from watchlists to avoid silent errors.
