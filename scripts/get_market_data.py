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

try:
    import yfinance as yf
except ModuleNotFoundError:
    print("Error: Missing dependency 'yfinance'. Activate your venv.", file=sys.stderr)
    sys.exit(1)

# --- CONFIGURATION ---
# Default Cache TTL values (seconds)
DEFAULT_TTL = {
    'hv': 86400,        # 24 hours
    'iv': 900,          # 15 minutes
    'price': 600,       # 10 minutes
    'earnings': 604800, # 7 days
    'sector': 2592000   # 30 days
}

try:
    with open('config/system_config.json', 'r') as f:
        SYS_CONFIG = json.load(f)
    DB_PATH = SYS_CONFIG.get('market_cache_db_path', '.market_cache.db')
    TTL = SYS_CONFIG.get('cache_ttl_seconds', DEFAULT_TTL)
except FileNotFoundError:
    DB_PATH = '.market_cache.db'
    TTL = DEFAULT_TTL

try:
    with open('config/market_config.json', 'r') as f:
        _config = json.load(f)
    SKIP_EARNINGS = set(_config.get('SKIP_EARNINGS', []))
    SKIP_SYMBOLS = set(_config.get('SKIP_SYMBOLS', []))
    SYMBOL_MAP = _config.get('SYMBOL_MAP', {})
    SECTOR_OVERRIDES = _config.get('SECTOR_OVERRIDES', {})
    FUTURES_PROXY = _config.get('FUTURES_PROXY', {})
    DATA_FETCHING = _config.get('DATA_FETCHING', {})
    DTE_MIN = DATA_FETCHING.get('dte_window_min', 25)
    DTE_MAX = DATA_FETCHING.get('dte_window_max', 50)
    TARGET_DTE = DATA_FETCHING.get('target_dte', 30)
    STRIKE_LOWER = DATA_FETCHING.get('strike_limit_lower', 0.8)
    STRIKE_UPPER = DATA_FETCHING.get('strike_limit_upper', 1.2)
except FileNotFoundError:
    SKIP_EARNINGS = set()
    SKIP_SYMBOLS = set()
    SYMBOL_MAP = {}
    SECTOR_OVERRIDES = {}
    FUTURES_PROXY = {}
    DTE_MIN = 25
    DTE_MAX = 50
    TARGET_DTE = 30
    STRIKE_LOWER = 0.8
    STRIKE_UPPER = 1.2

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

# --- HELPER FUNCTIONS ---
def normalize_iv(raw_iv: float, hv_context: Optional[float] = None) -> Tuple[float, Optional[str]]:
    """
    Normalize IV based on HV context to detect scale (decimal vs percentage).

    Args:
        raw_iv: Raw IV value from data source
        hv_context: Annualized realized volatility in percentage points (e.g., 15.5 for 15.5%)

    Returns:
        (normalized_iv, warning_flag)
    """
    # Case 1: Clear Percentage (e.g., 12.5, 50.0)
    if raw_iv > 1.0:
        return raw_iv, None

    # Case 2: Ambiguous (e.g., 0.5) -> Could be 0.5% or 50%
    implied_decimal_iv = raw_iv * 100

    # If no context, use decimal standard
    if hv_context is None or hv_context == 0:
        return implied_decimal_iv, None

    # Calculate biases under both interpretations
    bias_if_decimal = implied_decimal_iv / hv_context
    bias_if_percent = raw_iv / hv_context

    # Detect percentage format: If treating as decimal yields absurd bias (>10x)
    # but treating as percentage yields normal bias (0.5-3x)
    if bias_if_decimal > 10.0 and 0.5 <= bias_if_percent <= 3.0:
        return raw_iv, "iv_scale_corrected_percent"

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

# --- RESILIENT DATA FETCHING ---
def calculate_hv(ticker_obj: Any, symbol_key: str) -> Optional[float]:
    cache_key = f"hv_{symbol_key}"
    cached = cache.get(cache_key)
    if cached is not None: return cached

    def _fetch():
        hist = ticker_obj.history(period="1y", auto_adjust=True)
        if len(hist) < 200: return None
        adj_close = hist['Close'].dropna()
        if len(adj_close) < 200: return None
        log_ret = np.log(adj_close / adj_close.shift(1)).dropna()
        if log_ret.empty: return None
        return log_ret.std() * np.sqrt(252) * 100 

    try:
        val = retry_fetch(_fetch)
        if val is not None: cache.set(cache_key, val, TTL.get('hv', 86400))
        return val
    except: return None

def get_current_iv(ticker_obj: Any, current_price: float, symbol_key: str, hv_context: Optional[float] = None) -> Optional[Dict[str, Any]]:
    cache_key = f"iv_{symbol_key}"
    cached = cache.get(cache_key)
    if cached is not None:
        if isinstance(cached, dict): return cached
        try: return {'iv': float(cached), 'atm_vol': None, 'atm_bid': None, 'atm_ask': None}
        except: return None

    def _fetch():
        exps = ticker_obj.options
        if not exps: return None

        target_date = None
        today = datetime.now().date()
        min_diff = 999
        best_exp = None

        # Strict DTE_MIN-DTE_MAX DTE window
        for exp_str in exps:
            exp_date = datetime.strptime(exp_str, '%Y-%m-%d').date()
            days_out = (exp_date - today).days
            if DTE_MIN <= days_out <= DTE_MAX:
                target_date = exp_str
                break
            diff = abs(days_out - TARGET_DTE)
            if diff < min_diff:
                min_diff = diff
                best_exp = exp_str

        if not target_date: target_date = best_exp
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
            calls = _prep(band_calls if not band_calls.empty else calls).sort_values('dist').head(50)
            puts = _prep(band_puts if not band_puts.empty else puts).sort_values('dist').head(50)
        else:
            calls = _prep(calls).sort_values('dist').head(50)
            puts = _prep(puts).sort_values('dist').head(50)

        if calls.empty or puts.empty: return None

        atm_call = calls.nsmallest(1, 'dist').iloc[0]
        atm_put = puts.nsmallest(1, 'dist').iloc[0]

        # Zero Liquidity Check
        c_bid, c_ask = atm_call.get('bid', 0), atm_call.get('ask', 0)
        p_bid, p_ask = atm_put.get('bid', 0), atm_put.get('ask', 0)
        if (c_bid == 0 and c_ask == 0) or (p_bid == 0 and p_ask == 0): return None

        raw_iv = np.nanmean([atm_call.get('impliedVolatility', np.nan), atm_put.get('impliedVolatility', np.nan)])

        # Unit Auto-Correction via Context-Aware Normalization
        iv, warning = normalize_iv(raw_iv, hv_context)

        if np.isnan(iv) or iv <= 0: return None

        atm_vol = np.nansum([atm_call.get('volume', 0), atm_put.get('volume', 0)])
        result = {
            'iv': float(iv),
            'atm_vol': float(atm_vol) if not np.isnan(atm_vol) else 0,
            'atm_bid': float(c_bid + p_bid) / 2,
            'atm_ask': float(c_ask + p_ask) / 2
        }
        if warning:
            result['warning'] = warning
        return result

    try:
        val = retry_fetch(_fetch)
        if val is not None and val.get('iv', 0) > 0:
            cache.set(cache_key, val, TTL.get('iv', 900))
        return val
    except: return None

def get_price(ticker_obj: Any, symbol_key: str) -> Optional[Tuple[float, bool]]:
    cache_key = f"price_{symbol_key}"
    cached = cache.get(cache_key)
    if cached is not None: return cached
        
    def _fetch():
        try:
            p = ticker_obj.fast_info.last_price
            if p: return (p, False)
        except: pass
        try:
            hist = ticker_obj.history(period="1d", interval="1m")
            if not hist.empty: return (hist['Close'].iloc[-1], True)
        except: pass
        return None

    try:
        val = retry_fetch(_fetch, retries=2)
        if val is not None: cache.set(cache_key, val, TTL.get('price', 600))
        return val
    except: return None

def get_proxy_iv_and_hv(raw_symbol: str) -> Tuple[Optional[float], Optional[float], Optional[str]]:
    proxy = FUTURES_PROXY.get(raw_symbol[:3])
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
            etf_sym = proxy['etf_symbol']
            etf_t = yf.Ticker(etf_sym)
            etf_data = get_market_data([etf_sym]).get(etf_sym, {})
            iv = etf_data.get('iv')
            hv = etf_data.get('hv252')
            note = f"IV via {etf_sym}"
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
    except:
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

    price_data = get_price(ticker, yf_symbol)
    if not price_data:
        return raw_symbol, {"error": "no_price"}
    current_price, is_stale = price_data
    if current_price is None or current_price <= 0:
        return raw_symbol, {"error": "bad_price"}

    # Fetch HV and IV
    hv_val = calculate_hv(ticker, yf_symbol)
    iv_payload = get_current_iv(ticker, current_price, yf_symbol, hv_context=hv_val)

    iv_val = iv_payload.get('iv') if iv_payload else None
    atm_vol = iv_payload.get('atm_vol') if iv_payload else None
    atm_bid = iv_payload.get('atm_bid') if iv_payload else None
    atm_ask = iv_payload.get('atm_ask') if iv_payload else None
    iv_warning = iv_payload.get('warning') if iv_payload else None

    proxy_note = None
    if iv_val is None or hv_val is None:
        proxy_iv, proxy_hv, note = get_proxy_iv_and_hv(raw_symbol)
        if iv_val is None and proxy_iv is not None:
            iv_val = proxy_iv
            proxy_note = note
        if hv_val is None and proxy_hv is not None:
            hv_val = proxy_hv
            proxy_note = note if note else proxy_note

    if iv_val is None or hv_val is None or hv_val == 0:
        return raw_symbol, {"error": "insufficient_iv_hv"}

    vol_bias = iv_val / hv_val if hv_val else None
    if vol_bias is None or vol_bias <= 0:
        return raw_symbol, {"error": "invalid_vol_bias"}

    earnings_date = get_earnings_date(ticker, raw_symbol, yf_symbol)

    sector = SECTOR_OVERRIDES.get(raw_symbol, None) or ticker.info.get('sector', 'Unknown')

    data = {
        "price": current_price,
        "is_stale": is_stale,
        "iv": iv_val,
        "hv252": hv_val,
        "vol_bias": vol_bias,
        "atm_volume": atm_vol,
        "atm_bid": atm_bid,
        "atm_ask": atm_ask,
        "earnings_date": earnings_date,
        "sector": sector,
        "proxy": proxy_note
    }
    if iv_warning: data['warning'] = iv_warning
    cache.set(f"md_{yf_symbol}", data, TTL.get('price', 600))
    return raw_symbol, data

def get_market_data(symbols: List[str]) -> Dict[str, Dict[str, Any]]:
    """
    Fetch market data for a list of symbols concurrently with resilience and caching.
    """
    result: Dict[str, Dict[str, Any]] = {}
    symbols = list(set(symbols))  # Deduplicate

    # Attempt cache first
    for sym in list(symbols):
        cached = cache.get(f"md_{map_symbol(sym) or sym}")
        if cached:
            result[sym] = cached
            symbols.remove(sym)

    if not symbols:
        return result

    # Concurrent fetch for misses
    with futures.ThreadPoolExecutor(max_workers=min(8, len(symbols))) as executor:
        future_to_sym = {executor.submit(process_single_symbol, sym): sym for sym in symbols}
        for future in futures.as_completed(future_to_sym):
            sym = future_to_sym[future]
            try:
                key, data = future.result()
                result[key] = data
            except Exception as exc:
                result[sym] = {"error": str(exc)}

    return result

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Fetch market data for symbols.')
    parser.add_argument('symbols', nargs='+', help='Symbols to fetch')
    args = parser.parse_args()

    data = get_market_data(args.symbols)
    print(json.dumps(data, indent=2))
