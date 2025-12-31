from ..config_loader import load_market_config, load_system_config, load_trading_rules

DEFAULT_TTL = {
    "hv": 86400,  # 24 hours
    "iv": 900,  # 15 minutes
    "price": 600,  # 10 minutes
    "market_data": 86400,  # 24 hours
    "earnings": 604800,  # 7 days
    "sector": 2592000,  # 30 days
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
