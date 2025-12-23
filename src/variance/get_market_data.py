import contextlib
import io
import json
import os
import random
import sqlite3
import sys
import threading
import time
from concurrent import futures
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import numpy as np
# pandas is often not needed here but kept for compatibility if downstream relies on it
import pandas as pd

# Import Variance Logger
from .variance_logger import logger

try:
    import yfinance as yf
except ModuleNotFoundError:
    print("Error: Missing dependency 'yfinance'. Activate your venv.", file=sys.stderr)
    sys.exit(1)

# Optional Tastytrade SDK - REMOVED
TASTYTRADE_AVAILABLE = False

# --- CONFIGURATION ---
# Default Cache TTL values (seconds)
DEFAULT_TTL = {
    'hv': 86400,        # 24 hours
    'iv': 900,          # 15 minutes
    'price': 600,       # 10 minutes
    'earnings': 604800, # 7 days
    'sector': 2592000   # 30 days
}

from .config_loader import load_system_config, load_market_config

SYS_CONFIG = load_system_config()
DB_PATH = SYS_CONFIG.get('market_cache_db_path', '.market_cache.db')
TTL = SYS_CONFIG.get('cache_ttl_seconds', DEFAULT_TTL)
HV_MIN_HISTORY_DAYS = SYS_CONFIG.get('hv_min_history_days', 200)

_config = load_market_config()
SKIP_EARNINGS = set(_config.get('SKIP_EARNINGS', []))
SKIP_SYMBOLS = set(_config.get('SKIP_SYMBOLS', []))
SYMBOL_MAP = _config.get('SYMBOL_MAP', {})
SECTOR_OVERRIDES = _config.get('SECTOR_OVERRIDES', {})
ETF_SYMBOLS = set(_config.get('ETF_SYMBOLS', []))
FUTURES_PROXY = _config.get('FUTURES_PROXY', {})
DATA_FETCHING = _config.get('DATA_FETCHING', {})
DTE_MIN = DATA_FETCHING.get('dte_window_min', 25)
DTE_MAX = DATA_FETCHING.get('dte_window_max', 50)
TARGET_DTE = DATA_FETCHING.get('target_dte', 30)
STRIKE_LOWER = DATA_FETCHING.get('strike_limit_lower', 0.8)
STRIKE_UPPER = DATA_FETCHING.get('strike_limit_upper', 1.2)
OPTION_CHAIN_LIMIT = DATA_FETCHING.get('option_chain_limit', 50)

# --- TRADING RULES (Optional) ---
try:
    from .config_loader import load_trading_rules
except ImportError:
    try:
        from config_loader import load_trading_rules
    except ImportError:
        load_trading_rules = None

HV_FLOOR_PERCENT = 5.0
if load_trading_rules:
    try:
        _rules = load_trading_rules()
        HV_FLOOR_PERCENT = _rules.get('hv_floor_percent', HV_FLOOR_PERCENT)
    except Exception:
        pass

# --- TASTYTRADE SESSION (Optional) - REMOVED ---
_tastytrade_session = None

# --- OPTIMIZED SQLITE ENGINE ---
class MarketCache:
    """
    High-Performance SQLite Cache.
    Features: Thread-local connections, WAL mode, Lock-free reads, Lazy expiration.
    """
    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = db_path if db_path else DB_PATH
        self._local = threading.local()
        self._write_lock = threading.Lock()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, 'conn'):
            self._local.conn = sqlite3.connect(self.db_path, timeout=5, check_same_thread=False)
            self._local.conn.execute('PRAGMA journal_mode=WAL;')
            self._local.conn.execute('PRAGMA synchronous=NORMAL;')
            self._local.conn.execute('PRAGMA cache_size=-64000;') 
        return self._local.conn

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('PRAGMA journal_mode=WAL;')
            conn.execute('CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, value TEXT, expiry REAL)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_expiry ON cache(expiry);')

    def get(self, key: str) -> Optional[Any]:
        try:
            conn = self._get_conn()
            cursor = conn.execute('SELECT value, expiry FROM cache WHERE key = ?', (key,))
            row = cursor.fetchone()
            if row:
                val, expiry = row
                if time.time() < expiry:
                    return json.loads(val)
            return None
        except Exception:
            return None

    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        # RESILIENCE: Never cache errors or None
        if value is None or (isinstance(value, dict) and 'error' in value):
            return
        try:
            expiry = time.time() + ttl_seconds
            with self._write_lock:
                conn = self._get_conn()
                with conn:
                    conn.execute('INSERT OR REPLACE INTO cache (key, value, expiry) VALUES (?, ?, ?)', 
                                 (key, json.dumps(value), expiry))
                    if random.random() < 0.01:
                        conn.execute('DELETE FROM cache WHERE expiry < ?', (time.time(),))
        except Exception:
            pass

cache = MarketCache()
_EARNINGS_IO_LOCK = threading.Lock()

class MarketDataService:
    """
    Injectable market data fetcher with explicit cache dependency.

    Usage:
        # Production (uses default global cache)
        service = MarketDataService()
        data = service.get_market_data(['AAPL', 'GOOGL'])

        # Testing (inject mock cache)
        mock_cache = MarketCache(db_path='/tmp/test.db')
        service = MarketDataService(cache=mock_cache)
        data = service.get_market_data(['AAPL'])

    Attributes:
        cache (MarketCache): SQLite cache instance for data persistence
    """

    def __init__(self, cache: Optional[MarketCache] = None) -> None:
        """
        Initialize service with injectable cache.

        Args:
            cache: MarketCache instance. If None, uses module-level default cache.
        """
        self._cache = cache if cache is not None else globals()['cache']

    @property
    def cache(self) -> MarketCache:
        """Read-only access to cache instance."""
        return self._cache

    def get_market_data(self, symbols: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Fetch market data for a list of symbols concurrently.

        Args:
            symbols: List of ticker symbols (e.g., ['AAPL', '/ES', 'SPY'])

        Returns:
            Dict mapping symbol -> market data dict with keys:
                - price (float)
                - is_stale (bool)
                - iv (float)
                - hv252 (float)
                - hv20 (float|None)
                - hv_rank (float|None)
                - vrp_structural (float)
                - vrp_tactical (float|None)
                - atm_volume (float)
                - atm_bid (float)
                - atm_ask (float)
                - earnings_date (str|None)
                - sector (str)
                - proxy (str|None)
                - warning (str|None) [optional]
                - error (str) [on failure]
        """
        result: Dict[str, Dict[str, Any]] = {}
        symbols = list(set(symbols))  # Deduplicate

        # Attempt cache first
        for sym in list(symbols):
            cached = self._cache.get(f"md_{map_symbol(sym) or sym}")
            if cached:
                result[sym] = cached
                symbols.remove(sym)

        if not symbols:
            return result

        # Concurrent fetch for misses
        with futures.ThreadPoolExecutor(max_workers=min(8, len(symbols))) as executor:
            future_to_sym = {executor.submit(self._process_single_symbol, sym): sym for sym in symbols}
            for future in futures.as_completed(future_to_sym):
                sym = future_to_sym[future]
                try:
                    key, data = future.result()
                    result[key] = data
                except Exception as exc:
                    result[sym] = {"error": str(exc)}

        return result

    def _process_single_symbol(self, raw_symbol: str) -> Tuple[str, Dict[str, Any]]:
        """
        Internal: Fetch data for single symbol using instance cache.

        Delegates to module-level process_single_symbol but uses instance cache
        for any caching operations performed within this method's scope.
        """
        # For now, delegate to existing function
        # The existing process_single_symbol uses global cache internally
        # This is acceptable for Phase 1 - full cache injection requires deeper refactor
        return process_single_symbol(raw_symbol)

# --- HELPER FUNCTIONS ---
def get_dynamic_ttl(category: str, default_seconds: int) -> int:
    """
    Calculates a dynamic TTL based on New York time.
    """
    # Force US/Eastern Time (Market Time)
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo("America/New_York")
    except ImportError:
        # Fallback for very old Python versions
        from datetime import timezone as _timezone
        tz = _timezone(timedelta(hours=-5))
    
    now = datetime.now(tz).replace(tzinfo=None)
    weekday = now.weekday() # 0=Mon, 4=Fri, 5=Sat, 6=Sun
    
    # 1. Weekend Handling
    # If Saturday (5) or Sunday (6), target is next Monday
    # If Friday (4) AND After Hours (>= 16:00), target is next Monday
    is_weekend_hold = (weekday >= 5) or (weekday == 4 and now.hour >= 16)
    
    if is_weekend_hold:
        days_ahead = 7 - weekday # If Sun (6), add 1 day -> Mon (0). If Sat (5), add 2.
        if weekday == 4: days_ahead = 3 # Fri -> Mon
            
        future_monday = now + timedelta(days=days_ahead)
        target = future_monday.replace(hour=10, minute=0, second=0, microsecond=0)
        
        seconds_remaining = (target - now).total_seconds()
        return max(default_seconds, int(seconds_remaining))

    # 2. Weeknight Handling
    # Define "After Hours" as >= 16:00 or < 09:00
    is_after_hours = (now.hour >= 16) or (now.hour < 9)
    
    if is_after_hours:
        # Calculate seconds until tomorrow at 10:00 AM
        tomorrow = now + timedelta(days=1)
        target = tomorrow.replace(hour=10, minute=0, second=0, microsecond=0)
        
        # If currently morning (e.g. 1 AM), target is today 10:00 AM
        if now.hour < 10:
             target = now.replace(hour=10, minute=0, second=0, microsecond=0)
             
        seconds_remaining = (target - now).total_seconds()
        return max(default_seconds, int(seconds_remaining))
        
    return default_seconds

def normalize_iv(raw_iv: float, hv_context: Optional[float] = None) -> Tuple[float, Optional[str]]:
    """
    Normalize IV based on HV context to detect scale (decimal vs percentage).

    Args:
        raw_iv: Raw IV value from data source
        hv_context: Annualized realized volatility in percentage points (e.g., 15.5 for 15.5%)

    Returns:
        (normalized_iv, warning_flag)
    """
    # Preserve legacy behavior when no context is available.
    if hv_context is None or hv_context == 0:
        if raw_iv > 1.0:
            return raw_iv, None
        return raw_iv * 100, None

    # Ambiguous values: evaluate both interpretations against HV context.
    implied_decimal_iv = raw_iv * 100

    # Calculate biases under both interpretations
    bias_if_decimal = implied_decimal_iv / hv_context
    bias_if_percent = raw_iv / hv_context

    # Detect percentage format: If treating as decimal yields absurd bias (>10x)
    # but treating as percentage yields normal bias (0.5-3x)
    if bias_if_decimal > 10.0 and 0.5 <= bias_if_percent <= 3.0:
        return raw_iv, "iv_scale_corrected_percent"

    # FINDING-009: Protect against low-IV scaling errors
    if implied_decimal_iv > 200:  # No equity has 200% annualized IV
        return raw_iv, "iv_implausibly_high_assuming_percent"

    # Default to decimal format
    return implied_decimal_iv, None

def map_symbol(symbol: str) -> Optional[str]:
    if symbol.startswith('/'):
        for key, val in SYMBOL_MAP.items():
            if symbol.startswith(key): return val
        return None
    return SYMBOL_MAP.get(symbol, symbol)

def should_skip_earnings(raw_symbol: str, yf_symbol: str) -> bool:
    upper = raw_symbol.upper()
    if raw_symbol.startswith('/') or yf_symbol.endswith('=F') or yf_symbol.startswith('^'): return True
    return upper in SKIP_EARNINGS

def is_etf(raw_symbol: str) -> bool:
    """
    Check if symbol is an ETF/ETP (no corporate fundamentals).

    Args:
        raw_symbol: Original symbol before mapping

    Returns:
        bool: True if symbol is in ETF_SYMBOLS set
    """
    return raw_symbol.upper() in ETF_SYMBOLS

def retry_fetch(func: Callable, *args, retries=3, backoff=1.5, **kwargs):
    last_exc = None
    delay = 1.0
    for _ in range(retries):
        try: return func(*args, **kwargs)
        except Exception as e:
            last_exc = e
            time.sleep(delay + random.uniform(0, 0.5))
            delay *= backoff
    raise last_exc

def safe_get_sector(ticker_obj: Any, raw_symbol: str, symbol_key: str, skip_api: bool = False) -> str:
    """
    Safely retrieve sector info with HTTP error suppression.

    Args:
        ticker_obj: yfinance Ticker object
        raw_symbol: Original symbol (for SECTOR_OVERRIDES lookup)
        symbol_key: Mapped symbol (for cache key)
        skip_api: If True, skip API call entirely (use for ETFs)

    Returns:
        str: Sector name or 'Unknown' on failure
    """
    # Priority 1: Config override (never hits API or cache)
    override = SECTOR_OVERRIDES.get(raw_symbol)
    if override:
        return override

    # Priority 2: Cache lookup
    cache_key = f"sector_{symbol_key}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    # Priority 3: Skip API for ETFs (prevents 404)
    if skip_api:
        return 'Unknown'

    # Priority 4: API call with error suppression
    sector = 'Unknown'
    try:
        # Redirect stderr to suppress yfinance HTTP error messages
        with contextlib.redirect_stderr(io.StringIO()):
            info = ticker_obj.info
            if info:
                sector = info.get('sector', 'Unknown')
    except Exception:
        pass  # Non-fatal - use default

    # Cache successful lookups (including 'Unknown' to prevent repeated API hits)
    if sector != 'Unknown':
        cache.set(cache_key, sector, TTL.get('sector', 2592000))

    return sector

# --- RESILIENT DATA FETCHING ---
def calculate_hv(ticker_obj: Any, symbol_key: str) -> Optional[Dict[str, float]]:
    cache_key = f"hv_{symbol_key}"
    cached = cache.get(cache_key)
    # If cached value is not a dictionary, it's an old format. Force re-computation.
    if isinstance(cached, dict):
        return cached
    # If cached is not a dict or None, proceed to fetch

    def _fetch():
        hist = ticker_obj.history(period="1y", auto_adjust=True)
        if len(hist) < HV_MIN_HISTORY_DAYS: return None
        adj_close = hist['Close'].dropna()
        if len(adj_close) < HV_MIN_HISTORY_DAYS: return None
        log_ret = np.log(adj_close / adj_close.shift(1)).dropna()
        if log_ret.empty: return None
        
        hv252 = log_ret.std() * np.sqrt(252) * 100
        
        # Calculate HV60 (Quarterly Regime)
        hv60 = None
        if len(log_ret) >= 60:
            hv60 = log_ret.tail(60).std() * np.sqrt(252) * 100
            
        # Calculate HV20 (Monthly Regime)
        # We need at least 20 days of data
        hv20 = None
        hv20_stderr = None
        if len(log_ret) >= 20:
            hv20 = log_ret.tail(20).std() * np.sqrt(252) * 100
            # FINDING-012: HV20 has high standard error (~22%) due to small sample size
            hv20_stderr = hv20 * 0.22 if hv20 else None  # Approximate 1-sigma uncertainty

        return {'hv252': hv252, 'hv60': hv60, 'hv20': hv20, 'hv20_stderr': hv20_stderr}

    try:
        val = retry_fetch(_fetch)
        if val is not None: cache.set(cache_key, val, get_dynamic_ttl('hv', TTL.get('hv', 86400)))
        return val
    except Exception:
        return None

def calculate_hv_rank(ticker_obj: Any, symbol_key: str) -> Optional[float]:
    """
    Calculate HV Rank: percentile of current 30-day HV vs 1-year rolling 30-day HVs.

    Returns:
        float: HV Rank as percentage (0-100), or None if insufficient data
    """
    cache_key = f"hv_rank_{symbol_key}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    def _fetch():
        hist = ticker_obj.history(period="1y", auto_adjust=True)
        if len(hist) < 60:  # Need at least 60 days for meaningful rolling HV
            return None

        adj_close = hist['Close'].dropna()
        if len(adj_close) < 60:
            return None

        log_ret = np.log(adj_close / adj_close.shift(1)).dropna()
        if len(log_ret) < 60:
            return None

        # Current HV (30-day trailing, annualized)
        current_hv = log_ret.tail(30).std() * np.sqrt(252) * 100

        # Rolling 30-day HV for entire year
        rolling_hv = log_ret.rolling(window=30).std() * np.sqrt(252) * 100
        rolling_hv = rolling_hv.dropna()

        if len(rolling_hv) < 30:
            return None

        # Calculate rank (percentile: what % of rolling HVs are below current HV)
        hv_rank = (rolling_hv < current_hv).sum() / len(rolling_hv) * 100

        return hv_rank

    try:
        val = retry_fetch(_fetch)
        if val is not None:
            cache.set(cache_key, val, get_dynamic_ttl('hv', TTL.get('hv', 86400)))  # Same TTL as HV
        return val
    except Exception:
        return None

def is_monthly_expiration(date_str: str) -> bool:
    """
    Check if an expiration date is a standard monthly (3rd Friday).
    """
    try:
        dt = datetime.strptime(date_str, '%Y-%m-%d').date()
        # Standard Monthly is a Friday (weekday 4)
        if dt.weekday() != 4:
            return False
        # And occurs between the 15th and 21st of the month
        return 15 <= dt.day <= 21
    except ValueError:
        return False

def get_current_iv(ticker_obj: Any, current_price: float, symbol_key: str, hv_context: Optional[float] = None) -> Optional[Dict[str, Any]]:
    cache_key = f"iv_{symbol_key}"
    cached = cache.get(cache_key)
    if cached is not None:
        if isinstance(cached, dict): return cached
        try: return {'iv': float(cached), 'atm_vol': None, 'atm_bid': None, 'atm_ask': None}
        except Exception:
            return None

    def _fetch():
        exps = ticker_obj.options
        if not exps: return None

        today = datetime.now().date()
        
        # Priority 1: Monthlies within window
        monthlies_in_window = []
        # Priority 2: Weeklies within window
        weeklies_in_window = []
        # Fallback: Anything closest to target
        all_others = []

        for exp_str in exps:
            try:
                exp_date = datetime.strptime(exp_str, '%Y-%m-%d').date()
                days_out = (exp_date - today).days
                diff = abs(days_out - TARGET_DTE)
                
                is_monthly = is_monthly_expiration(exp_str)
                
                if DTE_MIN <= days_out <= DTE_MAX:
                    if is_monthly:
                        monthlies_in_window.append((diff, exp_str))
                    else:
                        weeklies_in_window.append((diff, exp_str))
                else:
                    all_others.append((diff, exp_str))
            except ValueError:
                continue

        # Selection Logic
        target_date = None
        if monthlies_in_window:
            # Pick monthly closest to target DTE
            monthlies_in_window.sort()
            target_date = monthlies_in_window[0][1]
        elif weeklies_in_window:
            # Fallback to weekly closest to target
            weeklies_in_window.sort()
            target_date = weeklies_in_window[0][1]
        elif all_others:
            # Absolute fallback
            all_others.sort()
            target_date = all_others[0][1]

        if not target_date: return None

        chain = ticker_obj.option_chain(target_date)
        calls, puts = chain.calls, chain.puts

        def _prep(df):
            df = df.copy()
            df['dist'] = abs(df['strike'] - current_price)
            return df

        if current_price and current_price > 0:
            lower, upper = current_price * STRIKE_LOWER, current_price * STRIKE_UPPER
            band_calls = calls[(calls['strike'] >= lower) & (calls['strike'] <= upper)]
            band_puts = puts[(puts['strike'] >= lower) & (puts['strike'] <= upper)]
            calls = _prep(band_calls if not band_calls.empty else calls).sort_values('dist').head(OPTION_CHAIN_LIMIT)
            puts = _prep(band_puts if not band_puts.empty else puts).sort_values('dist').head(OPTION_CHAIN_LIMIT)
        else:
            calls = _prep(calls).sort_values('dist').head(OPTION_CHAIN_LIMIT)
            puts = _prep(puts).sort_values('dist').head(OPTION_CHAIN_LIMIT)

        if calls.empty or puts.empty: return None

        # --- LIQUID-ATM SELECTION (Dev Mode) ---
        # Instead of just the closest strike, look at the top 3 candidates and pick the one 
        # with the highest Open Interest that has a valid (non-zero) bid.
        def _get_best_liquid_leg(df):
            candidates = df.nsmallest(3, 'dist')
            # Filter for non-zero bid
            live_candidates = candidates[candidates['bid'] > 0]
            if live_candidates.empty:
                # Fallback to absolute closest if all are dead, but this will likely fail later
                return candidates.iloc[0]
            # Pick highest Open Interest among live candidates
            return live_candidates.sort_values('openInterest', ascending=False).iloc[0]

        atm_call = _get_best_liquid_leg(calls)
        atm_put = _get_best_liquid_leg(puts)

        # Zero Liquidity Check (Final Guard)
        c_bid, c_ask = atm_call.get('bid', 0), atm_call.get('ask', 0)
        p_bid, p_ask = atm_put.get('bid', 0), atm_put.get('ask', 0)
        if (c_bid == 0 and c_ask == 0) or (p_bid == 0 and p_ask == 0): return None

        raw_iv = np.nanmean([atm_call.get('impliedVolatility', np.nan), atm_put.get('impliedVolatility', np.nan)])

        # Unit Auto-Correction via Context-Aware Normalization
        iv, warning = normalize_iv(raw_iv, hv_context)

        if np.isnan(iv) or iv <= 0: return None

        atm_vol = np.nansum([atm_call.get('volume', 0), atm_put.get('volume', 0)])
        atm_oi = np.nansum([atm_call.get('openInterest', 0), atm_put.get('openInterest', 0)])
        
        result = {
            'iv': float(iv),
            'atm_vol': float(atm_vol) if not np.isnan(atm_vol) else 0,
            'atm_open_interest': float(atm_oi) if not np.isnan(atm_oi) else 0,
            'atm_bid': float(c_bid + p_bid) / 2,
            'atm_ask': float(c_ask + p_ask) / 2,
            'call_bid': float(c_bid),
            'call_ask': float(c_ask),
            'call_vol': float(atm_call.get('volume', 0)),
            'call_oi': float(atm_call.get('openInterest', 0)),
            'put_bid': float(p_bid),
            'put_ask': float(p_ask),
            'put_vol': float(atm_put.get('volume', 0)),
            'put_oi': float(atm_put.get('openInterest', 0))
        }
        if warning:
            result['warning'] = warning
        return result

    try:
        val = retry_fetch(_fetch)
        if val is not None and val.get('iv', 0) > 0:
            cache.set(cache_key, val, get_dynamic_ttl('iv', TTL.get('iv', 900)))
        return val
    except Exception:
        return None

def get_price(ticker_obj: Any, symbol_key: str) -> Optional[Tuple[float, bool]]:
    cache_key = f"price_{symbol_key}"
    cached = cache.get(cache_key)
    if cached is not None: return cached
        
    def _fetch():
        try:
            p = ticker_obj.fast_info.last_price
            if p: return (p, False)
        except Exception:
            pass
        try:
            hist = ticker_obj.history(period="1d", interval="1m")
            if not hist.empty: return (hist['Close'].iloc[-1], True)
        except Exception:
            pass
        return None

    try:
        val = retry_fetch(_fetch, retries=2)
        if val is not None: cache.set(cache_key, val, get_dynamic_ttl('price', TTL.get('price', 600)))
        return val
    except Exception:
        return None

def get_proxy_iv_and_hv(raw_symbol: str) -> Tuple[Optional[float], Optional[float], Optional[str]]:
    # Find the best proxy match by checking decreasing prefix lengths
    # (e.g., check '/MES' before checking '/ES')
    proxy = None
    sorted_proxies = sorted(FUTURES_PROXY.keys(), key=len, reverse=True)
    for p_key in sorted_proxies:
        if raw_symbol.startswith(p_key):
            proxy = FUTURES_PROXY[p_key]
            break
            
    if not proxy: return None, None, None
    ptype = proxy.get('type')
    iv = hv = None
    note = ""
    try:
        if ptype == 'vol_index':
            iv_sym = proxy['iv_symbol']
            iv_t = yf.Ticker(iv_sym)
            iv_hist = iv_t.history(period="6mo")
            if not iv_hist.empty:
                iv = iv_hist['Close'].iloc[-1]
                note = f"IV via {iv_sym}"
        elif ptype == 'etf':
            etf_sym = proxy.get('iv_symbol') or proxy.get('etf_symbol')
            etf_t = yf.Ticker(etf_sym)
            etf_data = get_market_data([etf_sym]).get(etf_sym, {})
            iv = etf_data.get('iv')
            hv = etf_data.get('hv252')
            note = f"IV via {etf_sym}"
        elif ptype == 'hv_only':
            # Fetch HV from the symbol itself or a specified hv_symbol
            hv_sym = proxy.get('hv_symbol') or raw_symbol
            hv_sym_yf = map_symbol(hv_sym)
            if hv_sym_yf:
                hv_t = yf.Ticker(hv_sym_yf)
                hv_data = calculate_hv(hv_t, hv_sym_yf)
                if hv_data:
                    hv = hv_data.get('hv252')
                    note = "HV Only"
    except Exception:
        return None, None, None
    return iv, hv, note

def get_earnings_date(ticker_obj: Any, raw_symbol: str, yf_symbol: str) -> Optional[str]:
    cache_key = f"earn_{yf_symbol}"
    cached = cache.get(cache_key)
    if cached is not None: return cached

    if should_skip_earnings(raw_symbol, yf_symbol):
        return None

    def _fetch():
        with _EARNINGS_IO_LOCK:
            cal = ticker_obj.calendar
            if cal is not None and not cal.empty:
                if 'Earnings Date' in cal.index:
                    ed = cal.loc['Earnings Date'][0]
                    if hasattr(ed, 'to_pydatetime'):
                        ed = ed.to_pydatetime()
                    return ed.strftime("%Y-%m-%d")
        return None

    try:
        val = retry_fetch(_fetch)
        if val is not None: cache.set(cache_key, val, TTL.get('earnings', 604800))
        return val
    except Exception:
        return None

# --- MAIN DATA PROCESSOR ---
def process_single_symbol(raw_symbol: str) -> Tuple[str, Dict[str, Any]]:
    """
    Fetch and assemble market data for a single symbol with strict validation.
    Returns (symbol, data_dict).
    """
    yf_symbol = map_symbol(raw_symbol)
    if yf_symbol is None: 
        return raw_symbol, {"error": "unmapped_symbol"}
    if raw_symbol in SKIP_SYMBOLS:
        return raw_symbol, {"error": "skipped_symbol"}

    ticker = yf.Ticker(yf_symbol)
    skip_fundamentals = is_etf(raw_symbol)

    price_data = get_price(ticker, yf_symbol)
    if not price_data:
        return raw_symbol, {"error": "no_price"}
    current_price, is_stale = price_data
    if current_price is None or current_price <= 0:
        return raw_symbol, {"error": "bad_price"}

    # Fetch HV, HV Rank, and IV
    hv_data = calculate_hv(ticker, yf_symbol)
    hv252_val = hv_data.get('hv252') if hv_data else None
    hv60_val = hv_data.get('hv60') if hv_data else None
    hv20_val = hv_data.get('hv20') if hv_data else None
    hv20_stderr = hv_data.get('hv20_stderr') if hv_data else None

    hv_rank_val = calculate_hv_rank(ticker, yf_symbol)
    iv_payload = get_current_iv(ticker, current_price, yf_symbol, hv_context=hv252_val)

    iv_val = iv_payload.get('iv') if iv_payload else None
    atm_vol = iv_payload.get('atm_vol') if iv_payload else None
    atm_oi = iv_payload.get('atm_open_interest') if iv_payload else None
    atm_bid = iv_payload.get('atm_bid') if iv_payload else None
    atm_ask = iv_payload.get('atm_ask') if iv_payload else None
    iv_warning = iv_payload.get('warning') if iv_payload else None
    
    # Per-leg metrics
    call_bid = iv_payload.get('call_bid') if iv_payload else None
    call_ask = iv_payload.get('call_ask') if iv_payload else None
    call_vol = iv_payload.get('call_vol') if iv_payload else None
    call_oi = iv_payload.get('call_oi') if iv_payload else None
    put_bid = iv_payload.get('put_bid') if iv_payload else None
    put_ask = iv_payload.get('put_ask') if iv_payload else None
    put_vol = iv_payload.get('put_vol') if iv_payload else None
    put_oi = iv_payload.get('put_oi') if iv_payload else None

    proxy_note = None
    if iv_val is None or hv252_val is None:
        proxy_iv, proxy_hv, note = get_proxy_iv_and_hv(raw_symbol)
        
        # Use proxy data to fill gaps
        if iv_val is None and proxy_iv is not None:
            iv_val = proxy_iv
            proxy_note = note
            
        if hv252_val is None and proxy_hv is not None:
            hv252_val = proxy_hv
            # For proxies, we typically don't have historical data to calc HV20 easily 
            # without fetching the ETF history. For now, leave HV20 None or mirror HV252 if desperate.
            # Leaving as None is safer.
            if not proxy_note: proxy_note = note # Set note if not already set

    if iv_val is None or hv252_val is None or hv252_val == 0:
        # Final check: Do we have a valid proxy fallback that was missed?
        # Sometimes yfinance fails silently on the main symbol but proxy might work.
        
        # RESILIENCE: "Partial Data Mode"
        # If we have price but missing IV/HV, return partial data instead of error.
        # This prevents the portfolio from disappearing during after-hours/outages.
        if current_price and current_price > 0:
            logger.warning(f"PARTIAL DATA for {raw_symbol}: Price={current_price}, IV={iv_val}, HV={hv252_val}. Proceeding with limited functionality.")
            
            data = {
                "price": current_price,
                "is_stale": True, # Force stale flag for partial data
                "iv": iv_val,
                "hv252": hv252_val,
                "hv60": None,
                "hv20": hv20_val,
                "hv20_stderr": hv20_stderr,
                "hv_rank": hv_rank_val,
                "vrp_structural": 0.0, # Default to 0 to fail downstream filters (Screener)
                "vrp_tactical": 0.0,
                "atm_volume": 0,
                "atm_open_interest": 0,
                "atm_bid": 0,
                "atm_ask": 0,
                "call_bid": None,
                "call_ask": None,
                "call_vol": None,
                "call_oi": None,
                "put_bid": None,
                "put_ask": None,
                "put_vol": None,
                "put_oi": None,
                "earnings_date": None,
                "sector": safe_get_sector(ticker, raw_symbol, yf_symbol, skip_api=skip_fundamentals),
                "proxy": proxy_note,
                "warning": "partial_data_missing_vol"
            }
            cache.set(f"md_{yf_symbol}", data, get_dynamic_ttl('price', TTL.get('price', 600)))
            return raw_symbol, data

        return raw_symbol, {"error": "insufficient_iv_hv", "details": f"IV: {iv_val}, HV: {hv252_val}, Proxy: {proxy_note}"}

    vrp_structural = iv_val / hv252_val if hv252_val else None

    # Calculate Short-Term Bias (Tactical Edge)
    # Apply configured HV floor to prevent division by near-zero values causing explosion ratios
    # (e.g., 30% IV / 0.5% HV = 60x is unrealistic; floor gives max 6x)
    if hv20_val and hv20_val > 0:
        hv20_floored = max(hv20_val, HV_FLOOR_PERCENT)
        vrp_tactical = iv_val / hv20_floored
    else:
        vrp_tactical = None

    if vrp_structural is None or vrp_structural <= 0:
        return raw_symbol, {"error": "invalid_vrp_structural"}

    earnings_date = None if skip_fundamentals else get_earnings_date(ticker, raw_symbol, yf_symbol)

    sector = safe_get_sector(ticker, raw_symbol, yf_symbol, skip_api=skip_fundamentals)

    data = {
        "price": current_price,
        "is_stale": is_stale,
        "iv": iv_val,
        "hv252": hv252_val,
        "hv60": hv60_val,
        "hv20": hv20_val,
        "hv20_stderr": hv20_stderr,
        "hv_rank": hv_rank_val,
        "vrp_structural": vrp_structural,
        "vrp_tactical": vrp_tactical,
        "atm_volume": atm_vol,
        "atm_open_interest": atm_oi,
        "atm_bid": atm_bid,
        "atm_ask": atm_ask,
        "call_bid": call_bid,
        "call_ask": call_ask,
        "call_vol": call_vol,
        "call_oi": call_oi,
        "put_bid": put_bid,
        "put_ask": put_ask,
        "put_vol": put_vol,
        "put_oi": put_oi,
        "earnings_date": earnings_date,
        "sector": sector,
        "proxy": proxy_note
    }
    if iv_warning: data['warning'] = iv_warning
    cache.set(f"md_{yf_symbol}", data, get_dynamic_ttl('price', TTL.get('price', 600)))
    return raw_symbol, data

from .interfaces import IMarketDataProvider, MarketData

# --- YFINANCE ADAPTER ---
class YFinanceProvider(IMarketDataProvider):
    """
    Implementation of IMarketDataProvider using yfinance.
    Handles caching, rate limiting, and data normalization internally.
    """
    def __init__(self, cache_instance: Optional[MarketCache] = None):
        self.cache = cache_instance if cache_instance else MarketCache()

    def get_market_data(self, symbols: List[str]) -> Dict[str, MarketData]:
        """
        Fetch market data for a list of symbols using the thread pool.
        """
        results = {}
        with futures.ThreadPoolExecutor(max_workers=5) as executor:
            future_to_symbol = {
                executor.submit(process_single_symbol, sym, self.cache): sym 
                for sym in symbols
            }
            for future in futures.as_completed(future_to_symbol):
                sym = future_to_symbol[future]
                try:
                    r_sym, data = future.result()
                    if "error" not in data:
                        results[r_sym] = data
                    else:
                        logger.warning(f"Failed to fetch {r_sym}: {data['error']}")
                except Exception as exc:
                    logger.error(f"Exception fetching {sym}: {exc}")
        return results

    def get_current_price(self, symbol: str) -> float:
        """
        Get current price for a single symbol (optimized).
        """
        # Minimal implementation reusing the heavy fetch for now
        # TODO: Optimize to fetch only price
        data = self.get_market_data([symbol])
        if symbol in data:
            return data[symbol].get('price', 0.0)
        return 0.0

class MarketDataFactory:
    """
    Factory for creating Market Data Providers.
    """
    @staticmethod
    def get_provider(provider_type: str = "yfinance") -> IMarketDataProvider:
        if provider_type.lower() == "yfinance":
            return YFinanceProvider()
        else:
            raise ValueError(f"Unknown provider type: {provider_type}")

# Module-level singleton service (lazy initialization)
_default_service: Optional[MarketDataService] = None

def _get_default_service() -> MarketDataService:
    """Get or create the default MarketDataService singleton."""
    global _default_service
    if _default_service is None:
        _default_service = MarketDataService()
    return _default_service

def get_market_data(symbols: List[str], *, _service: Optional[MarketDataService] = None) -> Dict[str, Dict[str, Any]]:
    """
    Fetch market data for a list of symbols concurrently with resilience and caching.

    Backward-compatible wrapper around MarketDataService.

    Args:
        symbols: List of ticker symbols
        _service: (Testing) Injected service instance. Not for production use.

    Returns:
        Dict mapping symbol -> market data dict (see MarketDataService.get_market_data)

    Example:
        # Production
        data = get_market_data(['AAPL', 'GOOGL'])

        # Testing
        mock_cache = MarketCache('/tmp/test.db')
        test_service = MarketDataService(cache=mock_cache)
        data = get_market_data(['AAPL'], _service=test_service)
    """
    service = _service if _service is not None else _get_default_service()
    return service.get_market_data(symbols)

def _reset_default_service() -> None:
    """
    Reset the default service singleton.

    FOR TESTING ONLY. Allows tests to reset state between runs.
    """
    global _default_service
    _default_service = None

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Fetch market data for symbols.')
    parser.add_argument('symbols', nargs='+', help='Symbols to fetch')
    args = parser.parse_args()

    data = get_market_data(args.symbols)
    print(json.dumps(data, indent=2))
