import yfinance as yf
import json
import sys
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import concurrent.futures # Still needed for retry_fetch but not for parallel symbol fetching
import sqlite3
import time
import os
import random
import io # Added for stderr redirection
import threading
import contextlib

# Symbols where earnings are meaningless or unavailable (ETFs, indexes, futures)
SKIP_EARNINGS = {
    # Indexes/ETPs/commodities
    'SPY', 'QQQ', 'IWM', 'DIA', 'VXX', 'TQQQ', 'TLT', 'USO', 'GLD', 'SLV',
    'XLE', 'XLU', 'XBI', 'SMH', 'VIX', 'FXE', 'EWZ', 'EEM', 'FXI', 'GDX',
    'XLF', 'UVIX', 'UVXY', 'KRE', 'SILJ', 'IBB', 'KWEB', 'EWJ',
    'IBIT', 'ETHA',
}

# Symbols to skip entirely (no reliable Yahoo pricing)
SKIP_SYMBOLS = {
    'XSP', 'LTHM',
}

# Mapping from Tasty/CLI format to Yahoo Finance
SYMBOL_MAP = {
    '/ES': 'ES=F',
    '/NQ': 'NQ=F',
    '/CL': 'CL=F',
    '/GC': 'GC=F',
    '/SI': 'SI=F',
    '/HG': 'HG=F',   # Copper
    '/HE': 'HE=F',   # Lean Hogs
    '/LE': 'LE=F',   # Live Cattle
    '/6E': '6E=F',
    '/6B': '6B=F',
    '/6J': '6J=F',
    '/6A': '6A=F',
    '/ZN': 'ZN=F',
    '/ZB': 'ZB=F',
    '/ZC': 'ZC=F',   # Corn
    '/ZS': 'ZS=F',   # Soybeans
    '/ZF': 'ZF=F',   # 5Y Note
    '/ZT': 'ZT=F',   # 2Y Note
    '/NG': 'NG=F',
    '/RTY': 'RTY=F',
    '/YM': 'YM=F',
    'SPX': '^SPX',
    'VIX': '^VIX',
    'DJX': '^DJI',
    'NDX': '^NDX',
    'RUT': '^RUT'
}

# Futures proxy map: provide IV/HV sources for futures roots
# type: 'vol_index' uses index price as IV30 proxy; 'etf' uses ETF options for IV30 and ETF prices for HV
FUTURES_PROXY = {
    # Equity index
    '/ES': {'type': 'vol_index', 'iv_symbol': '^VIX', 'hv_symbol': 'ES=F'},
    '/NQ': {'type': 'vol_index', 'iv_symbol': '^VXN', 'hv_symbol': 'NQ=F'},
    '/RTY': {'type': 'etf', 'iv_symbol': 'IWM', 'hv_symbol': 'RTY=F'},  # RVX unreliable on Yahoo
    '/YM': {'type': 'vol_index', 'iv_symbol': '^VXD', 'hv_symbol': 'YM=F'},
    # FX
    '/6E': {'type': 'etf', 'iv_symbol': 'FXE', 'hv_symbol': 'FXE'},
    '/6B': {'type': 'etf', 'iv_symbol': 'FXB', 'hv_symbol': 'FXB'},
    '/6C': {'type': 'etf', 'iv_symbol': 'FXC', 'hv_symbol': 'FXC'},
    '/6J': {'type': 'etf', 'iv_symbol': 'FXY', 'hv_symbol': 'FXY'},
    '/6A': {'type': 'etf', 'iv_symbol': 'FXA', 'hv_symbol': 'FXA'},
    # Rates/Treasuries
    '/ZN': {'type': 'etf', 'iv_symbol': 'IEF', 'hv_symbol': 'IEF'},
    '/ZB': {'type': 'etf', 'iv_symbol': 'TLT', 'hv_symbol': 'TLT'},
    '/ZF': {'type': 'etf', 'iv_symbol': 'IEF', 'hv_symbol': 'IEF'},
    '/ZT': {'type': 'etf', 'iv_symbol': 'SHY', 'hv_symbol': 'SHY'},
    '/SR3': {'type': 'etf', 'iv_symbol': 'SHV', 'hv_symbol': 'SHV'},  # low IV; best-effort proxy
    # Energy/Metals
    '/CL': {'type': 'etf', 'iv_symbol': 'USO', 'hv_symbol': 'USO'},
    '/NG': {'type': 'etf', 'iv_symbol': 'UNG', 'hv_symbol': 'UNG'},
    '/GC': {'type': 'etf', 'iv_symbol': 'GLD', 'hv_symbol': 'GLD'},
    '/SI': {'type': 'etf', 'iv_symbol': 'SLV', 'hv_symbol': 'SLV'},
    '/HG': {'type': 'etf', 'iv_symbol': 'CPER', 'hv_symbol': 'CPER'},
    # Ags/Livestock
    '/ZC': {'type': 'etf', 'iv_symbol': 'CORN', 'hv_symbol': 'CORN'},
    '/ZS': {'type': 'etf', 'iv_symbol': 'SOYB', 'hv_symbol': 'SOYB'},
    '/HE': {'type': 'hv_only'},  # no liquid proxy
    '/LE': {'type': 'hv_only'},
}

class MarketCache:
    def __init__(self, db_path='.market_cache.db'):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    def _connect(self):
        # Allow cross-thread use with a small busy timeout to reduce "database is locked" errors
        return sqlite3.connect(self.db_path, timeout=5, check_same_thread=False)

    def _init_db(self):
        with self._connect() as conn:
            conn.execute('PRAGMA journal_mode=WAL;')
            conn.execute('PRAGMA synchronous=NORMAL;')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS cache (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    expiry REAL
                )
            ''')

    def get(self, key):
        try:
            with self._lock:
                with self._connect() as conn:
                    cursor = conn.execute('SELECT value, expiry FROM cache WHERE key = ?', (key,))
                    row = cursor.fetchone()
                    if row:
                        val, expiry = row
                        if time.time() < expiry:
                            return json.loads(val)
                        else:
                            # Expired
                            conn.execute('DELETE FROM cache WHERE key = ?', (key,))
            return None
        except Exception as exc:
            print(f"[cache] get failed for {key}: {exc}", file=sys.stderr)
            return None

    def set(self, key, value, ttl_seconds):
        try:
            expiry = time.time() + ttl_seconds
            with self._lock:
                with self._connect() as conn:
                    conn.execute('INSERT OR REPLACE INTO cache (key, value, expiry) VALUES (?, ?, ?)', 
                                 (key, json.dumps(value), expiry))
        except Exception as exc:
            print(f"[cache] set failed for {key}: {exc}", file=sys.stderr)
            pass

cache = MarketCache()
_EARNINGS_IO_LOCK = threading.Lock()

def map_symbol(symbol):
    if symbol.startswith('/'):
        for key, val in SYMBOL_MAP.items():
            if symbol.startswith(key):
                return val
        # Unknown/legacy future code; skip to avoid noisy 404s
        return None
    return SYMBOL_MAP.get(symbol, symbol)

def should_skip_earnings(raw_symbol, yf_symbol):
    """
    Many ETFs, indexes, and futures produce noisy 404s for earnings.
    Skip the calendar lookup for known non-equity underlyings.
    """
    upper = raw_symbol.upper()
    if raw_symbol.startswith('/') or yf_symbol.endswith('=F') or yf_symbol.startswith('^'):
        return True
    return upper in SKIP_EARNINGS

def retry_fetch(func, *args, retries=3, backoff_factor=1.5, **kwargs):
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

def calculate_hv(ticker_obj, symbol_key):
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
            cache.set(cache_key, val, 86400)
        return val
    except Exception:
        return None

def get_current_iv(ticker_obj, current_price, symbol_key):
    cache_key = f"iv_{symbol_key}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

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
        
        iv = (atm_call['impliedVolatility'] + atm_put['impliedVolatility']) / 2 * 100
        return iv

    try:
        val = retry_fetch(_fetch)
        if val is not None:
            cache.set(cache_key, val, 900)
        return val
    except Exception:
        return None

def get_price(ticker_obj, symbol_key):
    cache_key = f"price_{symbol_key}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
        
    def _fetch():
        # Prioritize fast_info (Real-timeish)
        try:
            p = ticker_obj.fast_info.last_price
            if p: return (p, False) # Price, is_stale
        except:
            pass
        
        # Fallback to history (Stale if market closed/pre-market)
        try:
            hist = ticker_obj.history(period="1d", interval="1m")
            if not hist.empty:
                return (hist['Close'].iloc[-1], True)
        except:
            pass
        
        return None

    try:
        val = retry_fetch(_fetch, retries=2)
        if val is not None:
            cache.set(cache_key, val, 600)
        return val
    except:
        return None

def get_proxy_iv_and_hv(raw_symbol):
    """
    Return (iv30, hv100, proxy_note) for futures using proxy definitions.
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

def get_earnings_date(ticker_obj, symbol_key):
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
            cache.set(cache_key, val, 604800)
        return val
    except Exception:
        return None

def process_single_symbol(raw_symbol):
    if raw_symbol in SKIP_SYMBOLS:
        return raw_symbol, {'error': 'Skipped symbol (no reliable pricing)'}

    yf_symbol = map_symbol(raw_symbol)
    if yf_symbol is None:
        return raw_symbol, {'error': 'Unmapped/unsupported futures code'}

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
        iv = proxy_iv if is_proxy and proxy_iv is not None else get_current_iv(ticker, price, yf_symbol)
        earnings_date = "N/A" if should_skip_earnings(raw_symbol, yf_symbol) else get_earnings_date(ticker, yf_symbol)
        
        data = {
            'price': price,
            'is_stale': is_stale,
            'hv100': hv,
            'iv30': iv,
            'earnings_date': earnings_date
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

def get_market_data(symbols):
    results = {}
    # Use ThreadPoolExecutor for parallel fetching, with a conservative worker count
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        future_to_symbol = {executor.submit(process_single_symbol, sym): sym for sym in symbols}
        for future in concurrent.futures.as_completed(future_to_symbol):
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
