# Configuration Overview

Variance centralizes configuration in `/config` and loads it through `src/variance/config_loader.py`. This keeps runtime behavior aligned with the JSON files and makes dependency injection explicit.

## Config Directory Resolution
- Default: `<repo>/config` (resolved relative to `src/variance/config_loader.py`).
- Override: set `VARIANCE_CONFIG_DIR` to an absolute or relative path.

## Strict Mode
- Environment flag: `VARIANCE_STRICT_CONFIG=1`.
- Strict mode fails fast on missing or malformed JSON files.
- Non-strict mode prints warnings and returns empty objects for missing/malformed files.

## Bundle Shape
`load_config_bundle()` returns a dictionary with:
- `trading_rules` → `config/trading_rules.json`
- `market_config` → `config/runtime_config.json` (`market` section)
- `system_config` → `config/runtime_config.json` (`system` section)
- `screener_profiles` → `config/runtime_config.json` (`screener_profiles` section)
- `strategies` → `config/strategies.json` (validated + keyed by id)

## Overrides
`load_config_bundle(overrides=...)` deep-merges override values into the bundle. Example override shape:
```json
{
  "trading_rules": { "net_liquidity": 250000 },
  "system_config": { "watchlist_path": "watchlists/dev.csv" }
}
```

## Injection Guidance
- `analyze_portfolio(..., config=...)` accepts a bundle for deterministic tests.
- `screen_volatility(..., config_bundle=...)` accepts a bundle for deterministic tests.
- `get_market_data` loads config once at import time; use a custom service for testing.

## Config Ownership
- Trading thresholds, risk logic, and performance limits: `trading_rules.json`
- Market/futures mappings and proxy logic: `runtime_config.json` (`market`)
- File paths, cache settings, and watchlist defaults: `runtime_config.json` (`system`)
- Screener presets: `runtime_config.json` (`screener_profiles`)
- Strategy metadata: `strategies.json`

### New Parameters
- **TUI Performance:** `screener_tui_limit` (Default: 50). Controls the maximum number of symbols scanned when running in `--tui` mode to ensure responsive UI updates.

## Liquidity & Filtering
Variance enforces strict liquidity gates to prevent trading in "ghost towns" or wide markets. These rules are defined in `trading_rules.json`.

### Liquidity Modes
Control the primary liquidity check using the `liquidity_mode` key:
- `"open_interest"` (**Default**): Checks `atm_open_interest >= min_atm_open_interest`. Best for stability and off-hours analysis (RFC 004).
- `"volume"`: Checks `atm_volume >= min_atm_volume`. More sensitive to current-day activity but fragile after hours.

### Safety Nets
Regardless of mode, the following safety checks always apply:
- **Slippage Cap:** `max_slippage_pct` (Default: 0.05 or 5%). Rejects symbols where the Bid/Ask spread is > 5% of the mid-price.
- **Futures Exemption:** Symbols starting with `/` (e.g., `/ES`, `/CL`) bypass volume/OI checks due to data limitations but remain subject to slippage checks if chain data is available.
