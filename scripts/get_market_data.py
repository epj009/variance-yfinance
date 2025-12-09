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
import pandas as pd

# Dependency guardrail: fail fast with clear install guidance
try:
    import yfinance as yf
except ModuleNotFoundError:
    print("Error: Missing dependency 'yfinance'. Activate your venv and run `pip install -r requirements.txt`.", file=sys.stderr)
    sys.exit(1)

# Load System Config
try:
    with open('config/system_config.json', 'r') as f:
        SYS_CONFIG = json.load(f)
    DB_PATH = SYS_CONFIG.get('market_cache_db_path', '.market_cache.db')
    TTL = SYS_CONFIG.get('cache_ttl_seconds', {})
except FileNotFoundError:
    print("Warning: config/system_config.json not found. Using defaults.", file=sys.stderr)
    DB_PATH = '.market_cache.db'
    TTL = {'hv': 86400, 'iv': 900, 'price': 600, 'earnings': 604800, 'sector': 2592000}

# Load Market Config
try:
    with open('config/market_config.json', 'r') as f:
        _config = json.load(f)
    SKIP_EARNINGS = set(_config.get('SKIP_EARNINGS', []))
    SKIP_SYMBOLS = set(_config.get('SKIP_SYMBOLS', []))
    SYMBOL_MAP = _config.get('SYMBOL_MAP', {})
    SECTOR_OVERRIDES = _config.get('SECTOR_OVERRIDES', {})
    FUTURES_PROXY = _config.get('FUTURES_PROXY', {})
except FileNotFoundError:
    print("Warning: config/market_config.json not found. Using empty defaults.", file=sys.stderr)
    SKIP_EARNINGS = set()
    SKIP_SYMBOLS = set()
    SYMBOL_MAP = {}
    SECTOR_OVERRIDES = {}
    FUTURES_PROXY = {}

class MarketCache:
    """
    High-Performance SQLite Cache.
    Features: Thread-local connections, WAL mode, Lock-free reads, Lazy expiration.
    """
    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = db_path if db_path else DB_PATH
        # We use thread_local storage so each thread keeps its own open connection
        # This prevents the massive overhead of opening/closing the file 400x per run.
        self._local = threading.local()
        self._write_lock = threading.Lock() # Only lock for writes
        self._last_sweep = 0
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        """Get the persistent connection for the current thread."""
        if not hasattr(self._local, 'conn'):
            # Check_same_thread=False is safe because we map 1 conn per thread via _local
            self._local.conn = sqlite3.connect(self.db_path, timeout=5, check_same_thread=False)
            # Optimize SQLite for cache workload
            self._local.conn.execute('PRAGMA journal_mode=WAL;') # Allow concurrent readers
            self._local.conn.execute('PRAGMA synchronous=NORMAL;') # Faster writes, safe enough for cache
            self._local.conn.execute('PRAGMA cache_size=-64000;') # Use 64MB memory cache
        return self._local.conn

    def _init_db(self) -> None:
        """Initialize DB with a temporary connection."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('PRAGMA journal_mode=WAL;')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS cache (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    expiry REAL
                )
            ''')
            # Index expiry for fast cleanup sweeps
            conn.execute('CREATE INDEX IF NOT EXISTS idx_expiry ON cache(expiry);')

    def get(self, key: str) -> Optional[Any]:
        """
        Lock-free Read.
        Returns None if missing or expired. Does NOT delete on read (avoids write-lock).
        """
        try:
            conn = self._get_conn()
            # No python lock here. SQLite WAL handles concurrent reads perfectly.
            cursor = conn.execute('SELECT value, expiry FROM cache WHERE key = ?', (key,))
            row = cursor.fetchone()
            if row:
                val, expiry = row
                if time.time() < expiry:
                    return json.loads(val)
                # If expired, just return None. Don't DELETE here. 
                # Deleting requires a write lock and slows down the reader.
                # Let the 'set' method or background sweep handle cleanup.
            return None
        except Exception:
            return None

    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        """
        Write with Lock.
        """
        # Variance Upgrade: Never cache "None" or Error dictionaries
        if value is None or (isinstance(value, dict) and 'error' in value):
            return 
        
        try:
            expiry = time.time() + ttl_seconds
            
            # Writes still need serialization to avoid "Database is locked" on heavy contention
            with self._write_lock:
                conn = self._get_conn()
                with conn: # Context manager automatically commits
                    conn.execute('INSERT OR REPLACE INTO cache (key, value, expiry) VALUES (?, ?, ?)', 
                                 (key, json.dumps(value), expiry))
                    
                    # Opportunistic Hygiene: Prune 1% of the time to keep DB small
                    # This is better than checking time.time() every call
                    if random.random() < 0.01: 
                        conn.execute('DELETE FROM cache WHERE expiry < ?', (time.time(),))
        except Exception:
            pass

cache = MarketCache()
_EARNINGS_IO_LOCK = threading.Lock()

def map_symbol(symbol: str) -> Optional[str]:
    """
    Convert broker-specific symbols (e.g., /ES) to Yahoo Finance format (e.g., ES=F).
    
    Args:
        symbol: Broker symbol that may need mapping.
        
    Returns:
        Mapped Yahoo Finance symbol, or None if unmapped/unsupported.
    """
    if symbol.startswith('/'):
        for key, val in SYMBOL_MAP.items():
            if symbol.startswith(key):
                return val
        # Unknown/legacy future code; skip to avoid noisy 404s
        return None
    return SYMBOL_MAP.get(symbol, symbol)

def should_skip_earnings(raw_symbol: str, yf_symbol: str) -> bool:
    """
    Determine if earnings data should be skipped for a symbol (e.g., ETFs, Indexes).
    
    Many ETFs, indexes, and futures produce noisy 404s for earnings.
    Skip the calendar lookup for known non-equity underlyings.
    
    Args:
        raw_symbol: Raw broker symbol.
        yf_symbol: Yahoo Finance mapped symbol.
        
    Returns:
        True if earnings should be skipped, False otherwise.
    """
    upper = raw_symbol.upper()
    if raw_symbol.startswith('/') or yf_symbol.endswith('=F') or yf_symbol.startswith('^'):
        return True
    return upper in SKIP_EARNINGS

def retry_fetch(func: Callable[..., Any], *args: Any, retries: int = 3, backoff_factor: float = 1.5, **kwargs: Any) -> Any:
    """
    Execute a function with exponential backoff retries to handle transient network errors.
    
    Args:
        func: The function to execute.
        *args: Positional arguments to pass to func.
        retries: Maximum number of retry attempts.
        backoff_factor: Multiplier for sleep time between retries.
        **kwargs: Keyword arguments to pass to func.
        
    Returns:
        The return value of func.
        
    Raises:
        Exception: The last exception raised if all retries fail.
    """
    last_exception = None
    delay = 1.0
    
    for attempt in range(retries):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            last_exception = e
            time.sleep(delay + random.uniform(0, 0.5))
            delay *= backoff_factor
            
    raise last_exception

def calculate_hv(ticker_obj: Any, symbol_key: str) -> Optional[float]:
    """
    Calculate Annualized Historical Volatility (HV252) based on the last year of daily returns.
    
    Formula: StdDev(Log Returns) * sqrt(252) * 100
    
    Args:
        ticker_obj: yfinance Ticker object.
        symbol_key: Symbol string for cache key.
        
    Returns:
        Annualized volatility as percentage, or None if calculation fails.
    """
    cache_key = f"hv_{symbol_key}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    def _fetch():
        # Use adjusted closes to avoid dividend/split distortions in realized vol
        hist = ticker_obj.history(period="1y", auto_adjust=True)
        if len(hist) < 200:
            return None
        adj_close = hist['Close'].dropna()
        if len(adj_close) < 200:
            return None
        log_ret = np.log(adj_close / adj_close.shift(1)).dropna()
        if log_ret.empty:
            return None
        daily_std = log_ret.std()
        annualized_vol = daily_std * np.sqrt(252) * 100 
        return annualized_vol

    try:
        val = retry_fetch(_fetch)
        if val is not None:
            cache.set(cache_key, val, TTL.get('hv', 86400))
        return val
    except Exception:
        return None

def get_current_iv(ticker_obj: Any, current_price: float, symbol_key: str) -> Optional[Dict[str, Any]]:
    """
    Estimate Implied Volatility (IV30) using the option chain ~30 days out.
    
    Method:
    1. Find expiration closest to 30-45 DTE.
    2. Fetch option chain.
    3. Average the IV of the ATM Call and ATM Put.
    
    Args:
        ticker_obj: yfinance Ticker object.
        current_price: Current underlying price.
        symbol_key: Symbol string for cache key.
        
    Returns:
        Dictionary with 'iv', 'atm_vol', 'atm_bid', 'atm_ask', or None if unavailable.
    """
    cache_key = f"iv_{symbol_key}"
    cached = cache.get(cache_key)
    if cached is not None:
        # Backward compatibility: older cache entries may be a bare float
        if isinstance(cached, dict):
            return cached
        try:
            return {'iv': float(cached), 'atm_vol': None, 'atm_bid': None, 'atm_ask': None}
        except Exception:
            return None

    def _fetch():
        exps = ticker_obj.options
        if not exps:
            return None
            
        target_date = None
        today = datetime.now().date()
        min_diff = 999
        best_exp = None
        
        for exp_str in exps:
            exp_date = datetime.strptime(exp_str, '%Y-%m-%d').date()
            days_out = (exp_date - today).days
            if 25 <= days_out <= 50:
                target_date = exp_str
                break
            diff = abs(days_out - 30)
            if diff < min_diff:
                min_diff = diff
                best_exp = exp_str
        
        if not target_date:
            target_date = best_exp
            
        if not target_date:
            return None

        chain = ticker_obj.option_chain(target_date)
        calls = chain.calls
        puts = chain.puts

        # Guard against massive chains by limiting strikes to a reasonable band around spot,
        # but if the band wipes everything out (LEAPS-only, thin strikes), fall back to full chain.
        def _prep(df):
            df = df.copy()
            df['dist'] = abs(df['strike'] - current_price)
            return df

        if current_price and current_price > 0:
            lower = current_price * 0.8
            upper = current_price * 1.2
            band_calls = calls[(calls['strike'] >= lower) & (calls['strike'] <= upper)]
            band_puts = puts[(puts['strike'] >= lower) & (puts['strike'] <= upper)]
            if not band_calls.empty and not band_puts.empty:
                calls = _prep(band_calls).sort_values('dist').head(500)
                puts = _prep(band_puts).sort_values('dist').head(500)
            else:
                calls = _prep(calls).sort_values('dist').head(500)
                puts = _prep(puts).sort_values('dist').head(500)
        else:
            calls = _prep(calls).sort_values('dist').head(500)
            puts = _prep(puts).sort_values('dist').head(500)
        
        if calls.empty or puts.empty:
            return None
        
        atm_call = calls.nsmallest(1, 'dist').iloc[0]
        atm_put = puts.nsmallest(1, 'dist').iloc[0]
        
        iv = np.nanmean([atm_call.get('impliedVolatility', np.nan), atm_put.get('impliedVolatility', np.nan)]) * 100
        if np.isnan(iv):
            return None

        atm_vol = np.nansum([atm_call.get('volume', np.nan), atm_put.get('volume', np.nan)])
        atm_vol = None if np.isnan(atm_vol) else float(atm_vol)

        atm_bid = np.nanmean([atm_call.get('bid', np.nan), atm_put.get('bid', np.nan)])
        atm_bid = None if np.isnan(atm_bid) else float(atm_bid)

        atm_ask = np.nanmean([atm_call.get('ask', np.nan), atm_put.get('ask', np.nan)])
        atm_ask = None if np.isnan(atm_ask) else float(atm_ask)

        return {
            'iv': float(iv),
            'atm_vol': atm_vol,
            'atm_bid': atm_bid,
            'atm_ask': atm_ask
        }

    try:
        val = retry_fetch(_fetch)
        if val is not None:
            cache.set(cache_key, val, TTL.get('iv', 900))
        return val
    except Exception:
        return None

def get_price(ticker_obj: Any, symbol_key: str) -> Optional[Tuple[float, bool]]:
    """
    Fetch the current market price. Prefer 'fast_info' (real-time), fallback to daily history (stale).
    
    Args:
        ticker_obj: yfinance Ticker object.
        symbol_key: Symbol string for cache key.
    
    Returns:
        Tuple of (price, is_stale_bool), or None if price unavailable.
    """
    cache_key = f"price_{symbol_key}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
        
    def _fetch():
        # Prioritize fast_info (Real-timeish)
        try:
            p = ticker_obj.fast_info.last_price
            if p:
                return (p, False)  # Price, is_stale
        except Exception:
            pass
        
        # Fallback to history (Stale if market closed/pre-market)
        try:
            hist = ticker_obj.history(period="1d", interval="1m")
            if not hist.empty:
                return (hist['Close'].iloc[-1], True)
        except Exception:
            pass
        
        return None

    try:
        val = retry_fetch(_fetch, retries=2)
        if val is not None:
            cache.set(cache_key, val, TTL.get('price', 600))
        return val
    except Exception:
        return None

def get_proxy_iv_and_hv(raw_symbol: str) -> Tuple[Optional[float], Optional[float], Optional[str]]:
    """
    Return (iv30, hv252, proxy_note) for futures using proxy definitions.
    
    Proxies allow calculating Vol Bias for futures (like /CL) using ETF equivalents (like USO).
    
    Args:
        raw_symbol: Raw broker symbol (e.g., "/CL").
        
    Returns:
        Tuple of (iv30, hv252, proxy_note). Any value may be None if unavailable.
    """
    proxy = FUTURES_PROXY.get(raw_symbol[:3])
    if not proxy:
        return None, None, None
    ptype = proxy.get('type')
    iv = hv = None
    note = ""
    try:
        if ptype == 'vol_index':
            iv_sym = proxy['iv_symbol']
            iv_t = yf.Ticker(iv_sym)
            iv_price = None
            try:
                iv_price = iv_t.fast_info.last_price
            except Exception:
                pass
            if iv_price is None:
                hist = iv_t.history(period="1d")
                if not hist.empty:
                    iv_price = hist['Close'].iloc[-1]
            if iv_price:
                iv = iv_price
                hv_sym = proxy.get('hv_symbol', iv_sym)
                hv_t = yf.Ticker(hv_sym)
                hv = calculate_hv(hv_t, hv_sym)
                note = f"IV via {iv_sym}"
        elif ptype == 'etf':
            iv_sym = proxy['iv_symbol']
            hv_sym = proxy.get('hv_symbol', iv_sym)
            # IV from ETF option chain
            iv_t = yf.Ticker(iv_sym)
            price_data = get_price(iv_t, iv_sym)
            price = price_data[0] if price_data else None
            iv = get_current_iv(iv_t, price, iv_sym) if price else None
            # HV from ETF
            hv_t = yf.Ticker(hv_sym)
            hv = calculate_hv(hv_t, hv_sym)
            note = f"IV via {iv_sym}"
        elif ptype == 'hv_only':
            note = "HV only (no IV proxy)"
    except Exception:
        pass
    return iv, hv, note

def get_earnings_date(ticker_obj: Any, symbol_key: str) -> Optional[str]:
    """
    Fetch the next earnings date from Yahoo Finance calendar.
    
    Args:
        ticker_obj: yfinance Ticker object.
        symbol_key: Symbol string for cache key.
        
    Returns:
        ISO format date string, "Unavailable", or None if error.
    """
    cache_key = f"earnings_{symbol_key}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    def _fetch():
        # Suppress yfinance 404 noise without mutating global stdout/stderr
        buf_out, buf_err = io.StringIO(), io.StringIO()
        try:
            with _EARNINGS_IO_LOCK:
                with contextlib.redirect_stdout(buf_out), contextlib.redirect_stderr(buf_err):
                    cal = ticker_obj.calendar
            if not cal:
                return None
            if isinstance(cal, dict):
                dates = cal.get('Earnings Date')
                if dates and isinstance(dates, list) and len(dates) > 0:
                    return dates[0].isoformat()
            return "Unavailable"
        except Exception:
            return "Unavailable"

    try:
        val = retry_fetch(_fetch, retries=1)
        if val is not None:
            cache.set(cache_key, val, TTL.get('earnings', 604800))
        return val
    except Exception:
        return None

def get_sector(ticker_obj: Any, symbol_key: str) -> str:
    """
    Fetch the sector for a symbol. Checks manual overrides first, then Yahoo Finance info.
    
    Args:
        ticker_obj: yfinance Ticker object.
        symbol_key: Symbol string for cache key.
        
    Returns:
        Sector name string, or "Unknown" if unavailable.
    """
    # Check overrides first (handle raw symbols like /CL or mapped ETFs)
    # Note: symbol_key passed here is usually the mapped YF symbol (e.g., CL=F)
    # We need to check the raw symbol if possible, but here we only have ticker_obj and symbol_key.
    # Ideally, we check overrides in process_single_symbol using the raw_symbol.
    # But let's try to match mapped symbols back or just check known YF symbols in overrides.
    
    # However, let's keep it simple: check overrides in process_single_symbol instead.
    # This function will remain focused on fetching from YF if no override exists.
    
    cache_key = f"sector_{symbol_key}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    def _fetch():
        # Avoid expensive/404-prone lookups for futures and indices; rely on overrides instead
        if symbol_key.endswith("=F"):
            return "Futures"
        if symbol_key.startswith("^"):
            return "Index"
        try:
            # .info can be slow/flaky, but it's the only place for sector
            info = ticker_obj.info
            return info.get('sector', 'Unknown')
        except Exception:
            return "Unknown"

    try:
        # Cache for 30 days (sector unlikely to change)
        val = retry_fetch(_fetch, retries=1)
        if val is not None:
            cache.set(cache_key, val, TTL.get('sector', 2592000))
        return val
    except Exception:
        return "Unknown"

def process_single_symbol(raw_symbol: str) -> Tuple[str, Dict[str, Any]]:
    """
    Orchestrate the data fetching for a single symbol.
    
    Steps:
    1. Map symbol (e.g., /ES -> ES=F).
    2. Check for Futures Proxies (e.g., IV from VIX).
    3. Fetch Price, HV, IV, Earnings, Sector (parallelizable).
    4. Calculate Vol Bias.
    
    Args:
        raw_symbol: Raw broker symbol.
        
    Returns:
        Tuple of (symbol, data_dict). data_dict may contain 'error' key on failure.
    """
    if raw_symbol in SKIP_SYMBOLS:
        return raw_symbol, {'error': 'Skipped symbol (no reliable pricing)'}

    # CHECK OVERRIDES FIRST using raw_symbol
    override_sector = SECTOR_OVERRIDES.get(raw_symbol)
    if not override_sector:
        # Try checking the root for futures (e.g. /CLZ4 -> /CL)
        if raw_symbol.startswith('/'):
             root = raw_symbol[:3]
             override_sector = SECTOR_OVERRIDES.get(root)

    yf_symbol = map_symbol(raw_symbol)
    if yf_symbol is None:
        return raw_symbol, {'error': 'Unmapped/unsupported futures code'}
    
    # Also check override for the mapped symbol (e.g., GLD)
    if not override_sector:
        override_sector = SECTOR_OVERRIDES.get(yf_symbol)

    # Futures proxy path: try to supply IV/HV via proxies before standard chain
    proxy_iv = proxy_hv = None
    proxy_note = None
    is_proxy = False
    if raw_symbol.startswith('/'):
        proxy_iv, proxy_hv, proxy_note = get_proxy_iv_and_hv(raw_symbol)
        if proxy_iv is not None or proxy_hv is not None:
            is_proxy = True

    try:
        ticker = yf.Ticker(yf_symbol)
        
        price_data = get_price(ticker, yf_symbol)
        if price_data is None:
            return raw_symbol, {'error': 'No price found'}
            
        price, is_stale = price_data
            
        hv = proxy_hv if is_proxy and proxy_hv is not None else calculate_hv(ticker, yf_symbol)
        iv_data = proxy_iv if is_proxy and proxy_iv is not None else get_current_iv(ticker, price, yf_symbol)
        if iv_data is not None and not isinstance(iv_data, dict):
            # Proxy path uses a simple float; normalize to dict for downstream use
            iv_data = {'iv': iv_data, 'atm_vol': None, 'atm_bid': None, 'atm_ask': None}
        iv = iv_data['iv'] if iv_data else None
        liquidity = None
        if iv_data:
            liquidity = {
                'atm_vol': iv_data.get('atm_vol'),
                'atm_bid': iv_data.get('atm_bid'),
                'atm_ask': iv_data.get('atm_ask')
            }
        earnings_date = "N/A" if should_skip_earnings(raw_symbol, yf_symbol) else get_earnings_date(ticker, yf_symbol)
        
        if override_sector:
            sector = override_sector
        else:
            sector = get_sector(ticker, yf_symbol)
        
        data = {
            'price': price,
            'is_stale': is_stale,
            'hv252': hv,
            'iv30': iv,
            'liquidity': liquidity,
            'earnings_date': earnings_date,
            'sector': sector
        }
        
        if hv and iv:
            data['vol_bias'] = iv / hv
        elif iv is None and hv is not None:
            data['vol_bias'] = None

        if proxy_note:
            data['proxy'] = proxy_note
        
        return raw_symbol, data

    except Exception as e:
        return raw_symbol, {'error': str(e)}

def get_market_data(symbols: List[str]) -> Dict[str, Dict[str, Any]]:
    """
    Fetch market data for a list of symbols concurrently.
    
    Args:
        symbols: List of symbol strings (e.g., ['AAPL', '/ES']).
        
    Returns:
        A dictionary mapping symbol -> data dict.
    """
    results = {}
    # Use ThreadPoolExecutor for parallel fetching, with a conservative worker count
    with futures.ThreadPoolExecutor(max_workers=2) as executor:
        future_to_symbol = {executor.submit(process_single_symbol, sym): sym for sym in symbols}
        for future in futures.as_completed(future_to_symbol):
            sym, data = future.result()
            results[sym] = data
    return results

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({'error': 'Usage: python get_market_data.py SYMBOL [SYMBOL2 ...]'}))
        sys.exit(1)

    symbols_to_fetch = sys.argv[1:]
    data = get_market_data(symbols_to_fetch)
    print(json.dumps(data, indent=2))
