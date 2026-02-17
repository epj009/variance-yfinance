from ..config_loader import load_market_config, load_system_config, load_trading_rules

DEFAULT_TTL = {
    "hv": 86400,  # 24 hours (historical volatility - slow-moving)
    "iv": 900,  # 15 minutes (implied volatility - market hours)
    "price": 300,  # 5 minutes (current prices - market hours)
    "market_metrics": 900,  # 15 minutes (batch IV/liquidity data)
    "market_data": 900,  # 15 minutes (merged data) - FIX: was misleading 86400
    "option_chain": 86400,  # 24 hours (chain structure is stable)
    "option_quotes": 60,  # 1 minute (real-time bid/ask)
    "symbol_resolution": 604800,  # 7 days (DXLink symbol mapping)
    "earnings": 604800,  # 7 days
    "sector": 2592000,  # 30 days
}

# Extended TTLs for after-hours when data is static
AFTER_HOURS_TTL = {
    "iv": 28800,  # 8 hours (IV frozen after market close)
    "price": 14400,  # 4 hours (prices static)
    "market_metrics": 28800,  # 8 hours
    "market_data": 28800,  # 8 hours
    "option_quotes": 14400,  # 4 hours (quotes frozen)
}

SYS_CONFIG = load_system_config()
DB_PATH = SYS_CONFIG.get("market_cache_db_path", ".market_cache.db")
TTL = SYS_CONFIG.get("cache_ttl_seconds", DEFAULT_TTL)
HV_MIN_HISTORY_DAYS = SYS_CONFIG.get("hv_min_history_days", 200)

_config = load_market_config()
SKIP_EARNINGS = set(_config.get("SKIP_EARNINGS", []))
SKIP_SYMBOLS = set(_config.get("SKIP_SYMBOLS", []))
SYMBOL_MAP = _config.get("SYMBOL_MAP", {})
SECTOR_OVERRIDES = _config.get("SECTOR_OVERRIDES", {})
ETF_SYMBOLS = set(_config.get("ETF_SYMBOLS", []))
FUTURES_PROXY = _config.get("FUTURES_PROXY", {})
FAMILY_MAP = _config.get("FAMILY_MAP", {})
DATA_FETCHING = _config.get("DATA_FETCHING", {})

DTE_MIN = DATA_FETCHING.get("dte_window_min", 25)
DTE_MAX = DATA_FETCHING.get("dte_window_max", 50)
TARGET_DTE = DATA_FETCHING.get("target_dte", 30)
STRIKE_LOWER = DATA_FETCHING.get("strike_limit_lower", 0.8)
STRIKE_UPPER = DATA_FETCHING.get("strike_limit_upper", 1.2)
OPTION_CHAIN_LIMIT = DATA_FETCHING.get("option_chain_limit", 50)

HV_FLOOR_PERCENT = 5.0
try:
    _rules = load_trading_rules()
    HV_FLOOR_PERCENT = float(_rules.get("hv_floor_percent", HV_FLOOR_PERCENT))
except Exception:
    pass

__all__ = [
    "DEFAULT_TTL",
    "AFTER_HOURS_TTL",
    "DB_PATH",
    "TTL",
    "HV_MIN_HISTORY_DAYS",
    "SKIP_EARNINGS",
    "SKIP_SYMBOLS",
    "SYMBOL_MAP",
    "SECTOR_OVERRIDES",
    "ETF_SYMBOLS",
    "FUTURES_PROXY",
    "FAMILY_MAP",
    "DATA_FETCHING",
    "DTE_MIN",
    "DTE_MAX",
    "TARGET_DTE",
    "STRIKE_LOWER",
    "STRIKE_UPPER",
    "OPTION_CHAIN_LIMIT",
    "HV_FLOOR_PERCENT",
]
