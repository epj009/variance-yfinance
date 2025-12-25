import contextlib
import io
import json
import math
import sqlite3
import sys
import threading
import time
from concurrent import futures
from datetime import datetime
from datetime import time as pytime
from typing import Any, Optional, cast

import numpy as np
import pytz


def is_market_open() -> bool:
    """Checks if the NYSE is currently open."""
    tz = pytz.timezone("US/Eastern")
    now = datetime.now(tz)
    # Weekends
    if now.weekday() >= 5:
        return False
    # Standard Hours (9:30 AM - 4:00 PM ET)
    return pytime(9, 30) <= now.time() <= pytime(16, 0)


# Import Variance Logger

try:
    import yfinance as yf
except ModuleNotFoundError:
    print("Error: Missing dependency 'yfinance'. Activate your venv.", file=sys.stderr)
    sys.exit(1)

# --- CONFIGURATION ---
DEFAULT_TTL = {
    "hv": 86400,  # 24 hours
    "iv": 900,  # 15 minutes
    "price": 600,  # 10 minutes
    "earnings": 604800,  # 7 days
    "sector": 2592000,  # 30 days
}

from .config_loader import load_market_config, load_runtime_config, load_system_config

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
DATA_FETCHING = _config.get("DATA_FETCHING", {})
DTE_MIN = DATA_FETCHING.get("dte_window_min", 25)
DTE_MAX = DATA_FETCHING.get("dte_window_max", 50)
TARGET_DTE = DATA_FETCHING.get("target_dte", 30)
STRIKE_LOWER = DATA_FETCHING.get("strike_limit_lower", 0.8)
STRIKE_UPPER = DATA_FETCHING.get("strike_limit_upper", 1.2)
OPTION_CHAIN_LIMIT = DATA_FETCHING.get("option_chain_limit", 50)

try:
    from .config_loader import load_trading_rules

    HAS_TRADING_RULES = True
except ImportError:
    HAS_TRADING_RULES = False

HV_FLOOR_PERCENT = 5.0
if HAS_TRADING_RULES:
    try:
        from .config_loader import load_trading_rules

        _rules = load_trading_rules()
        HV_FLOOR_PERCENT = float(_rules.get("hv_floor_percent", HV_FLOOR_PERCENT))
    except Exception:
        pass


# --- OPTIMIZED SQLITE ENGINE ---
class MarketCache:
    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = db_path if db_path else str(DB_PATH)
        self._local = threading.local()
        self._write_lock = threading.Lock()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn"):
            self._local.conn = sqlite3.connect(self.db_path, timeout=5, check_same_thread=False)
            self._local.conn.execute("PRAGMA journal_mode=WAL;")
            self._local.conn.execute("PRAGMA synchronous=NORMAL;")
        return cast(sqlite3.Connection, self._local.conn)

    def _init_db(self) -> None:
        with self._write_lock:
            conn = self._get_conn()
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cache (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    expiry INTEGER
                )
            """)
            conn.commit()

    def get(self, key: str) -> Optional[Any]:
        conn = self._get_conn()
        now = int(time.time())
        cursor = conn.execute("SELECT value FROM cache WHERE key = ? AND expiry > ?", (key, now))
        row = cursor.fetchone()
        if row:
            try:
                return cast(Any, json.loads(str(row[0])))
            except json.JSONDecodeError:
                return None
        return None

    def get_any(self, key: str) -> Optional[Any]:
        """Return cached value even if expired (used for after-hours reads)."""
        conn = self._get_conn()
        cursor = conn.execute("SELECT value FROM cache WHERE key = ?", (key,))
        row = cursor.fetchone()
        if row:
            try:
                return cast(Any, json.loads(str(row[0])))
            except json.JSONDecodeError:
                return None
        return None

    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        if value is None:
            return
        with self._write_lock:
            conn = self._get_conn()
            expiry = int(time.time()) + ttl_seconds
            val_str = json.dumps(value)
            conn.execute(
                "INSERT OR REPLACE INTO cache (key, value, expiry) VALUES (?, ?, ?)",
                (key, val_str, expiry),
            )
            conn.commit()


cache = MarketCache()


# --- UTILITIES ---
def get_dynamic_ttl(data_type: str, default: int) -> int:
    return int(TTL.get(data_type, default))


def map_symbol(raw_symbol: str) -> Optional[str]:
    if not raw_symbol:
        return None
    if raw_symbol in SYMBOL_MAP:
        return SYMBOL_MAP[raw_symbol]  # type: ignore[no-any-return]
    if raw_symbol.startswith("/"):
        root = raw_symbol[1:3]
        if f"/{root}" in SYMBOL_MAP:
            return SYMBOL_MAP[f"/{root}"]  # type: ignore[no-any-return]
    return raw_symbol


def is_etf(symbol: str) -> bool:
    if isinstance(symbol, dict):
        return False  # Not an ETF if invalid input
    return symbol.upper() in ETF_SYMBOLS


def should_skip_earnings(raw_symbol: str, yf_symbol: str) -> bool:
    # Defensive: Handle case where parameters might be dicts
    if isinstance(raw_symbol, dict):
        return True  # Skip earnings for invalid input
    if isinstance(yf_symbol, dict):
        return True

    upper = raw_symbol.upper()
    if raw_symbol.startswith("/") or yf_symbol.endswith("=F") or yf_symbol.startswith("^"):
        return True
    return upper in SKIP_EARNINGS


def normalize_iv(iv_raw: float, hv_context: Optional[float] = None) -> tuple[float, Optional[str]]:
    if iv_raw is None or iv_raw <= 0:
        return 0.0, "iv_zero_or_none"
    if hv_context and hv_context > 0:
        dist_raw = abs(math.log(iv_raw / hv_context))
        dist_scaled = abs(math.log((iv_raw * 100) / hv_context))
        if dist_scaled < dist_raw:
            return iv_raw * 100, "iv_scale_corrected"
        return iv_raw, None
    if iv_raw < 1.5:
        return iv_raw * 100, "iv_scale_assumed_decimal"
    return iv_raw, None


def get_price(
    ticker_obj: Any, yf_symbol: str, cache: Optional[MarketCache] = None
) -> Optional[tuple[float, bool]]:
    local_cache = cache if cache else globals()["cache"]
    cache_key = f"price_{yf_symbol}"
    cached = local_cache.get(cache_key)
    if cached is not None:
        try:
            return float(cached), True
        except (TypeError, ValueError):
            pass

    try:
        # Use getattr to be safe with Mocks and different yfinance versions
        fast_info = getattr(ticker_obj, "fast_info", None)
        price = getattr(fast_info, "last_price", None)

        if price is not None:
            # Recursively drill down if we got a list/sequence
            while hasattr(price, "__len__") and not isinstance(price, (str, bytes, dict)):
                if len(price) > 0:
                    price = price[0]
                else:
                    return None

            price = float(price)
            if price > 0:
                local_cache.set(cache_key, price, get_dynamic_ttl("price", 600))
                return price, False
    except Exception:
        pass
    return None


def calculate_hv(
    ticker_obj: Any, yf_symbol: str, cache: Optional[MarketCache] = None
) -> Optional[dict[str, Any]]:
    local_cache = cache if cache else globals()["cache"]
    cache_key = f"hv_{yf_symbol}"
    cached = local_cache.get(cache_key)
    if cached:
        return cast(dict[str, Any], cached)
    try:
        hist = ticker_obj.history(period="2y")
        if len(hist) < HV_MIN_HISTORY_DAYS:
            return None
        returns = np.log(hist["Close"] / hist["Close"].shift(1)).dropna()

        def _vol(window: int) -> float:
            return float(returns.tail(window).std() * np.sqrt(252) * 100)

        res = {
            "hv252": _vol(252),
            "hv60": _vol(60),
            "hv20": _vol(20),
            "hv20_stderr": float(returns.tail(20).std() / np.sqrt(20) * np.sqrt(252) * 100),
            "raw_returns": returns.tolist(),  # Store list for JSON serialization
        }
        local_cache.set(cache_key, res, get_dynamic_ttl("hv", 86400))
        return res
    except Exception:
        return None


def get_current_iv(
    ticker_obj: Any,
    price: float,
    yf_symbol: str,
    hv_context: Optional[float] = None,
    cache: Optional[MarketCache] = None,
) -> dict[str, Any]:
    local_cache = cache if cache else globals()["cache"]
    cache_key = f"iv_{yf_symbol}"
    cached = local_cache.get(cache_key)
    if cached:
        return cast(dict[str, Any], cached)
    try:
        options = ticker_obj.options
        if not options:
            return {}
        target_date = None
        now = datetime.now()
        for opt_date in options:
            dte = (datetime.strptime(opt_date, "%Y-%m-%d") - now).days
            if DTE_MIN <= dte <= DTE_MAX:
                target_date = opt_date
                break
        if not target_date:
            target_date = options[0]
        chain = ticker_obj.option_chain(target_date)
        calls, puts = chain.calls, chain.puts
        if calls.empty or puts.empty:
            return {}

        # AFTER-HOURS CHECK: If bid/asks are zero, the live data is "Bad"
        is_zero_bid = (calls["bid"].sum() == 0 and calls["ask"].sum() == 0) or (
            puts["bid"].sum() == 0 and puts["ask"].sum() == 0
        )

        if is_zero_bid:
            return {}

        calls["dist"] = abs(calls["strike"] - price)
        puts["dist"] = abs(puts["strike"] - price)
        atm_call = calls.sort_values("dist").iloc[0]
        atm_put = puts.sort_values("dist").iloc[0]
        raw_iv = (atm_call["impliedVolatility"] + atm_put["impliedVolatility"]) / 2
        iv, warning = normalize_iv(raw_iv, hv_context)

        def _safe_float(value: Any, default: float = 0.0) -> float:
            try:
                if value is None:
                    return default
                val = float(value)
                if math.isnan(val):
                    return default
                return val
            except (TypeError, ValueError):
                return default

        atm_vol = int(_safe_float(atm_call.get("volume")) + _safe_float(atm_put.get("volume")))
        atm_oi = int(
            _safe_float(atm_call.get("openInterest")) + _safe_float(atm_put.get("openInterest"))
        )
        res = {
            "iv": iv,
            "warning": warning,
            "atm_volume": atm_vol,
            "atm_oi": atm_oi,
            "atm_bid": float((atm_call["bid"] + atm_put["bid"]) / 2),
            "atm_ask": float((atm_call["ask"] + atm_put["ask"]) / 2),
            "call_bid": float(atm_call["bid"]),
            "call_ask": float(atm_call["ask"]),
            "put_bid": float(atm_put["bid"]),
            "put_ask": float(atm_put["ask"]),
        }
        local_cache.set(cache_key, res, get_dynamic_ttl("iv", 900))
        return res
    except Exception:
        return {}


def get_earnings_date(
    ticker_obj: Any, raw_symbol: str, yf_symbol: str, cache: Optional[MarketCache] = None
) -> Optional[str]:
    local_cache = cache if cache else globals()["cache"]
    cache_key = f"earn_{yf_symbol}"
    cached = local_cache.get(cache_key)
    if cached is not None:
        return cast(Optional[str], cached)
    if should_skip_earnings(raw_symbol, yf_symbol):
        return None
    try:
        cal = ticker_obj.calendar
        if cal is not None and not cal.empty and "Earnings Date" in cal.index:
            ed = cal.loc["Earnings Date"][0]
            if hasattr(ed, "to_pydatetime"):
                ed = ed.to_pydatetime()
            val = str(ed.strftime("%Y-%m-%d"))
            local_cache.set(cache_key, val, TTL.get("earnings", 604800))
            return val
    except Exception:
        pass
    return None


def safe_get_sector(
    ticker_obj: Any,
    raw_symbol: str,
    yf_symbol: str,
    skip_api: bool = False,
    cache: Optional[MarketCache] = None,
) -> str:
    if raw_symbol in SECTOR_OVERRIDES:
        return str(SECTOR_OVERRIDES[raw_symbol])
    local_cache = cache if cache else globals()["cache"]
    cache_key = f"sec_{yf_symbol}"
    cached = local_cache.get(cache_key)
    if cached:
        return str(cached)
    if skip_api:
        return "Unknown"
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            sec = ticker_obj.info.get("sector", "Unknown")
        local_cache.set(cache_key, sec, TTL.get("sector", 2592000))
        return str(sec)
    except Exception:
        return "Unknown"


def process_single_symbol(
    raw_symbol: str, cache_instance: Optional[MarketCache] = None
) -> tuple[str, dict[str, Any]]:
    """
    Fetches and processes all metrics for a single ticker.
    Implements 'Bifurcated Proxy' logic for futures.
    """
    local_cache = cache_instance if cache_instance else globals()["cache"]
    market_is_open = is_market_open()

    # Defensive: Handle case where raw_symbol might be a dict (shouldn't happen)
    if isinstance(raw_symbol, dict):
        symbol_str = str(raw_symbol.get("symbol", "UNKNOWN"))
        return symbol_str, {
            "error": f"Invalid symbol type: dict with keys {list(raw_symbol.keys())}"
        }

    if raw_symbol in SKIP_SYMBOLS:
        return raw_symbol, {"error": "skipped_symbol"}

    cache_key = f"market_data_{raw_symbol}"
    cached_all = local_cache.get(cache_key)
    if cached_all is None:
        cached_all = local_cache.get(f"md_{raw_symbol}")
    if cached_all is None and not market_is_open:
        cached_all = local_cache.get_any(cache_key)
        if cached_all is None:
            cached_all = local_cache.get_any(f"md_{raw_symbol}")
    if cached_all:
        return raw_symbol, cast(dict[str, Any], cached_all)

    try:
        # 1. Resolve Symbols
        # yf_symbol is the 'Cleanest' version of the root (e.g. CL=F)
        # proxy_symbol is the IV proxy (e.g. USO) for futures screening.
        yf_symbol = map_symbol(raw_symbol) or raw_symbol

        # For futures, prefer ETF proxy from FAMILY_MAP for clock-aligned math
        proxy_symbol = None
        if raw_symbol.startswith("/"):
            market_config = load_market_config()
            family_map = market_config.get("FAMILY_MAP", {})

            # Find ETF in same family
            for _family_name, members in family_map.items():
                if raw_symbol in members:
                    for member in members:
                        if not member.startswith("/") and not member.startswith("^"):
                            proxy_symbol = member
                            break
                    if proxy_symbol:
                        break

        # If no FAMILY_MAP proxy, fall back to FUTURES_PROXY
        if not proxy_symbol:
            proxy_config = FUTURES_PROXY.get(raw_symbol)
            if isinstance(proxy_config, dict):
                proxy_symbol = proxy_config.get("iv_symbol")
            elif isinstance(proxy_config, str):
                proxy_symbol = proxy_config

        proxy_note = f"via {proxy_symbol}" if proxy_symbol else None
        is_futures = raw_symbol.startswith("/")

        if is_futures:
            futures_ticker = yf.Ticker(yf_symbol)
            price_data = get_price(futures_ticker, yf_symbol, cache=local_cache)
            if not price_data:
                return raw_symbol, {"error": "price_unavailable"}

            hv_data = calculate_hv(futures_ticker, yf_symbol, cache=local_cache)
            if not hv_data:
                return raw_symbol, {"error": "history_unavailable"}

            iv_data = {}
            if proxy_symbol:
                proxy_ticker = yf.Ticker(proxy_symbol)
                proxy_price = get_price(proxy_ticker, proxy_symbol, cache=local_cache)
                if proxy_price:
                    iv_data = get_current_iv(
                        proxy_ticker,
                        proxy_price[0],
                        proxy_symbol,
                        hv_data.get("hv20"),
                        cache=local_cache,
                    )

            if not iv_data:
                iv_data = get_current_iv(
                    futures_ticker,
                    price_data[0],
                    yf_symbol,
                    hv_data.get("hv20"),
                    cache=local_cache,
                )

            if not iv_data:
                iv_data = {"iv": None, "warning": "iv_unavailable"}

            sector = safe_get_sector(
                futures_ticker,
                raw_symbol,
                yf_symbol,
                skip_api=True,
                cache=local_cache,
            )
            earnings_date = get_earnings_date(
                futures_ticker, raw_symbol, yf_symbol, cache=local_cache
            )
        else:
            math_symbol = proxy_symbol if proxy_symbol else yf_symbol
            math_ticker = yf.Ticker(math_symbol)

            price_data = get_price(math_ticker, math_symbol, cache=local_cache)
            if not price_data:
                return raw_symbol, {"error": "price_unavailable"}

            hv_data = calculate_hv(math_ticker, math_symbol, cache=local_cache)
            if not hv_data:
                return raw_symbol, {"error": "history_unavailable"}

            iv_data = get_current_iv(
                math_ticker,
                price_data[0],
                math_symbol,
                hv_data.get("hv20"),
                cache=local_cache,
            )
            if not iv_data:
                iv_data = {"iv": None, "warning": "iv_unavailable"}

            sector = safe_get_sector(
                math_ticker,
                raw_symbol,
                math_symbol,
                skip_api=is_etf(math_symbol),
                cache=local_cache,
            )
            earnings_date = get_earnings_date(
                math_ticker, raw_symbol, math_symbol, cache=local_cache
            )

        # Combine and Cache
        iv = iv_data.get("iv")
        hv252 = hv_data.get("hv252")

        res = {
            "price": price_data[0],
            "is_stale": price_data[1] or not market_is_open,
            "iv": iv,
            "hv252": hv252,
            "hv20": hv_data.get("hv20"),
            "returns": list(hv_data.get("raw_returns", [])[-60:]),  # Last 60 days for correlation
            "vrp_structural": iv / hv252 if (hv252 and iv is not None) else None,
            "vrp_tactical": (
                iv / max(hv_data.get("hv20", 5.0), HV_FLOOR_PERCENT)
                if (hv_data.get("hv20") and iv is not None)
                else None
            ),
            "sector": sector,
            "earnings_date": earnings_date,
            "proxy": proxy_note,
        }
        res.update(iv_data)

        # Override staleness if market is closed
        if not market_is_open:
            res["is_stale"] = True

        # Set data_source for yfinance-only processing
        res["data_source"] = "yfinance"

        local_cache.set(cache_key, res, TTL.get("price", 600))
        return raw_symbol, res
    except Exception as e:
        import traceback

        error_trace = traceback.format_exc()
        return raw_symbol, {"error": str(e), "trace": error_trace[:500]}


from .interfaces import IMarketDataProvider, MarketData
from .tastytrade_client import TastytradeAuthError, TastytradeClient, TastytradeMetrics

__all__ = [
    "get_market_data",
    "MarketDataService",
    "MarketData",
    "YFinanceProvider",
    "TastytradeProvider",
    "MarketDataFactory",
]


class YFinanceProvider(IMarketDataProvider):
    def __init__(self, cache_instance: Optional[MarketCache] = None):
        self.cache = cache_instance if cache_instance else globals()["cache"]

    def get_market_data(self, symbols: list[str]) -> dict[str, MarketData]:
        unique_symbols = list(set(symbols))
        results: dict[str, MarketData] = {}

        # After-Hours Global Check
        market_is_open = is_market_open()

        with futures.ThreadPoolExecutor(max_workers=5) as executor:
            future_to_symbol = {
                executor.submit(process_single_symbol, s, self.cache): s for s in unique_symbols
            }
            for future in futures.as_completed(future_to_symbol):
                try:
                    sym, data = future.result()

                    # ENFORCEMENT: If market is closed, force is_stale to True
                    if not market_is_open and "error" not in data:
                        data["is_stale"] = True
                        data["data_source"] = "yfinance"

                    results[sym] = cast(MarketData, data)
                except Exception as e:
                    results[future_to_symbol[future]] = cast(MarketData, {"error": str(e)})
        return results


class TastytradeProvider(IMarketDataProvider):
    """
    Composite market data provider using Tastytrade for volatility metrics
    and yfinance for price/returns data.

    This provider:
    1. Fetches vol metrics (IV, HV30, HV90) from TastytradeClient
    2. Fetches price/returns from YFinanceProvider
    3. Merges both sources into composite MarketData
    4. Computes VRP using Tastytrade HV30/HV90
    5. Falls back to yfinance-only on auth errors
    """

    def __init__(
        self,
        cache_instance: Optional[MarketCache] = None,
        yf_fallback: Optional[YFinanceProvider] = None,
    ):
        """
        Initialize TastytradeProvider.

        Args:
            cache_instance: Optional MarketCache instance for caching
            yf_fallback: Optional YFinanceProvider for fallback (created if None)
        """
        self.cache = cache_instance if cache_instance else globals()["cache"]
        self.yf_provider = yf_fallback if yf_fallback else YFinanceProvider(cache_instance)

        # Try to initialize Tastytrade client (may raise TastytradeAuthError)
        self.tt_client: Optional[TastytradeClient]
        try:
            self.tt_client = TastytradeClient()
        except TastytradeAuthError:
            # Defer error until get_market_data() is called
            self.tt_client = None

    def get_market_data(self, symbols: list[str]) -> dict[str, MarketData]:
        """
        Fetch composite market data for symbols.

        Data Flow:
            1. Try: Fetch vol metrics from Tastytrade
            2. Fetch price/returns from yfinance (always)
            3. Merge: TT vol fields + yf price/returns
            4. Compute VRP using TT HV30/HV90
            5. Set data_source="composite"
            6. On TastytradeAuthError: fallback to yfinance-only with warning

        Args:
            symbols: List of ticker symbols

        Returns:
            Dictionary mapping symbols to MarketData objects
        """
        # If Tastytrade client is unavailable, fallback to yfinance-only
        if self.tt_client is None:
            results = self.yf_provider.get_market_data(symbols)
            # Mark all results with tastytrade_fallback warning
            for sym in results:
                if "error" not in results[sym]:
                    results[sym]["warning"] = "tastytrade_fallback"
                    results[sym]["data_source"] = "yfinance"
            return results

        # Try to fetch Tastytrade metrics
        try:
            tt_metrics = self.tt_client.get_market_metrics(symbols)
        except TastytradeAuthError:
            # Fallback to yfinance-only
            results = self.yf_provider.get_market_data(symbols)
            for sym in results:
                if "error" not in results[sym]:
                    results[sym]["warning"] = "tastytrade_fallback"
                    results[sym]["data_source"] = "yfinance"
            return results
        except Exception:
            # Network error or other issue - fallback
            results = self.yf_provider.get_market_data(symbols)
            for sym in results:
                if "error" not in results[sym]:
                    results[sym]["warning"] = "tastytrade_fallback"
                    results[sym]["data_source"] = "yfinance"
            return results

        # Always fetch yfinance data for price/returns
        yf_results = self.yf_provider.get_market_data(symbols)

        # Merge Tastytrade + yfinance data
        final_results: dict[str, MarketData] = {}
        for sym in symbols:
            final_results[sym] = self._merge_tastytrade_yfinance(
                sym, tt_metrics.get(sym), yf_results.get(sym)
            )

        return final_results

    def _merge_tastytrade_yfinance(
        self,
        symbol: str,
        tt_data: Optional[TastytradeMetrics],
        yf_data: Optional[MarketData],
    ) -> MarketData:
        """
        Merge Tastytrade vol metrics with yfinance price/returns data.

        Priority:
            - Price/returns: yfinance
            - IV/HV: Tastytrade (if available), else yfinance
            - VRP: Computed from Tastytrade HV30/HV90 (if available)

        Args:
            symbol: Ticker symbol
            tt_data: Tastytrade metrics (optional)
            yf_data: yfinance market data (optional)

        Returns:
            Composite MarketData object
        """
        # If no yfinance data, return error
        if not yf_data:
            return cast(MarketData, {"error": "yfinance_unavailable"})

        # If yfinance has error, propagate it
        if "error" in yf_data:
            return yf_data

        # Start with yfinance data as base
        merged = dict(yf_data)

        # If Tastytrade data available, overlay vol metrics
        if tt_data:
            # Overlay IV (Tastytrade already scaled to percent)
            if "iv" in tt_data and tt_data["iv"] is not None:
                merged["iv"] = tt_data["iv"]
                # Clear yfinance warning if Tastytrade IV is good
                if merged.get("warning") == "iv_unavailable":
                    merged["warning"] = None

            # Add Tastytrade-specific fields
            if "iv_rank" in tt_data and tt_data["iv_rank"] is not None:
                merged["iv_rank"] = tt_data["iv_rank"]

            if "iv_percentile" in tt_data and tt_data["iv_percentile"] is not None:
                merged["iv_percentile"] = tt_data["iv_percentile"]

            if "liquidity_rating" in tt_data and tt_data["liquidity_rating"] is not None:
                merged["liquidity_rating"] = tt_data["liquidity_rating"]

            if "liquidity_value" in tt_data and tt_data["liquidity_value"] is not None:
                merged["liquidity_value"] = tt_data["liquidity_value"]

            if "corr_spy_3month" in tt_data and tt_data["corr_spy_3month"] is not None:
                merged["corr_spy_3month"] = tt_data["corr_spy_3month"]

            if "beta" in tt_data and tt_data["beta"] is not None:
                merged["beta"] = tt_data["beta"]

            # Add HV30/HV90 for compression ratio calculations
            if "hv30" in tt_data and tt_data["hv30"] is not None:
                merged["hv30"] = tt_data["hv30"]

            if "hv90" in tt_data and tt_data["hv90"] is not None:
                merged["hv90"] = tt_data["hv90"]

            # Overlay earnings date (Tastytrade may be more accurate)
            if "earnings_date" in tt_data and tt_data["earnings_date"] is not None:
                merged["earnings_date"] = tt_data["earnings_date"]

            # Compute VRP using Tastytrade IV and best available HV (HV252 from YF preferred)
            merged = self._compute_vrp(merged, tt_data, yf_data)

            # Mark as composite source
            merged["data_source"] = "composite"
        else:
            # No Tastytrade data - mark as yfinance-only
            merged["data_source"] = "yfinance"

        return cast(MarketData, merged)

    def _compute_vrp(
        self,
        merged_data: dict[str, Any],
        tt_data: TastytradeMetrics,
        yf_data: Optional[MarketData] = None,
    ) -> dict[str, Any]:
        """
        Compute VRP (structural/tactical).

        Formulas:
            vrp_structural = IV / HV252 (YF) OR IV / HV90 (TT)
            vrp_tactical = IV / max(HV30, hv_floor)

        Args:
            merged_data: Merged market data dict
            tt_data: Tastytrade metrics with HV30/HV90
            yf_data: YFinance market data with HV252

        Returns:
            Updated merged_data with VRP fields
        """
        iv = merged_data.get("iv")
        if iv is None or iv <= 0:
            return merged_data

        # Structural VRP: Prefer HV252 (YF) -> Fallback HV90 (TT)
        hv252 = yf_data.get("hv252") if yf_data else None
        hv90 = tt_data.get("hv90")

        if hv252 is not None and hv252 > 0:
            merged_data["vrp_structural"] = iv / hv252
        elif hv90 is not None and hv90 > 0:
            merged_data["vrp_structural"] = iv / hv90

        # Tactical VRP: IV / max(HV30, floor)
        hv30 = tt_data.get("hv30")
        if hv30 is not None:
            hv_floor = HV_FLOOR_PERCENT  # From config (default 5.0)
            merged_data["vrp_tactical"] = iv / max(hv30, hv_floor)

        return merged_data


class MarketDataFactory:
    @staticmethod
    def get_provider(provider_type: str = "tastytrade") -> IMarketDataProvider:
        """
        Get market data provider by type.

        Args:
            provider_type: "tastytrade" (default) or "yfinance"

        Returns:
            IMarketDataProvider instance

        Raises:
            ValueError: If provider_type is unknown
        """
        provider_lower = provider_type.lower()

        if provider_lower == "tastytrade":
            # Try to create TastytradeProvider, fallback to yfinance on auth error
            try:
                return TastytradeProvider()
            except TastytradeAuthError:
                # Fallback to yfinance if Tastytrade auth fails
                return YFinanceProvider()

        if provider_lower == "yfinance":
            return YFinanceProvider()

        raise ValueError(f"Unknown provider type: {provider_type}")


class MarketDataService:
    def __init__(self, cache: Optional[MarketCache] = None):
        self._cache = cache if cache else globals()["cache"]

        # Load config to determine provider
        try:
            runtime_config = load_runtime_config()
            tt_config = runtime_config.get("tastytrade", {})
            use_tastytrade = tt_config.get("enabled", False)
        except Exception:
            # Fallback if config loading fails
            use_tastytrade = False

        if use_tastytrade:
            self.provider = MarketDataFactory.get_provider("tastytrade")
        else:
            self.provider = MarketDataFactory.get_provider("yfinance")

    @property
    def cache(self) -> MarketCache:
        return cast(MarketCache, self._cache)

    def get_market_data(self, symbols: list[str]) -> dict[str, MarketData]:
        return self.provider.get_market_data(symbols)


_default_service: Optional[MarketDataService] = None


def _get_default_service() -> MarketDataService:
    global _default_service
    if not _default_service:
        _default_service = MarketDataService()
    return _default_service


def get_market_data(
    symbols: list[str], _service: Optional[MarketDataService] = None
) -> dict[str, MarketData]:
    s = _service or _get_default_service()
    return s.get_market_data(symbols)


def _reset_default_service() -> None:
    global _default_service
    _default_service = None
