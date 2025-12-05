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

# Mapping from Tasty/CLI format to Yahoo Finance
SYMBOL_MAP = {
    '/ES': 'ES=F',
    '/NQ': 'NQ=F',
    '/CL': 'CL=F',
    '/GC': 'GC=F',
    '/SI': 'SI=F',
    '/6E': '6E=F',
    '/6B': '6B=F',
    '/6J': '6J=F',
    '/6A': '6A=F',
    '/ZN': 'ZN=F',
    '/ZB': 'ZB=F',
    '/NG': 'NG=F',
    '/RTY': 'RTY=F',
    '/YM': 'YM=F',
    'SPX': '^SPX',
    'VIX': '^VIX',
    'DJX': '^DJI',
    'NDX': '^NDX',
    'RUT': '^RUT'
}

class MarketCache:
    def __init__(self, db_path='.market_cache.db'):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS cache (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    expiry REAL
                )
            ''')

    def get(self, key):
        try:
            with sqlite3.connect(self.db_path) as conn:
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
        except Exception:
            return None

    def set(self, key, value, ttl_seconds):
        try:
            expiry = time.time() + ttl_seconds
            with sqlite3.connect(self.db_path) as conn:
                conn.execute('INSERT OR REPLACE INTO cache (key, value, expiry) VALUES (?, ?, ?)', 
                             (key, json.dumps(value), expiry))
        except Exception:
            pass

cache = MarketCache()

def map_symbol(symbol):
    if symbol.startswith('/'):
        for key, val in SYMBOL_MAP.items():
            if symbol.startswith(key):
                return val
        return symbol 
    return SYMBOL_MAP.get(symbol, symbol)

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
        hist = ticker_obj.history(period="1y")
        if len(hist) < 200:
            return None
        hist['log_ret'] = np.log(hist['Close'] / hist['Close'].shift(1))
        daily_std = hist['log_ret'].std()
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
        
        calls['dist'] = abs(calls['strike'] - current_price)
        puts['dist'] = abs(puts['strike'] - current_price)
        
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

def get_earnings_date(ticker_obj, symbol_key):
    cache_key = f"earnings_{symbol_key}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    def _fetch():
        # Temporarily redirect stderr to suppress yfinance's verbose 404 warnings
        original_stderr = sys.stderr
        sys.stderr = io.StringIO()
        try:
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
        finally:
            sys.stderr = original_stderr # Restore stderr

    try:
        val = retry_fetch(_fetch, retries=1)
        if val is not None:
            cache.set(cache_key, val, 604800)
        return val
    except Exception:
        return None

def process_single_symbol(raw_symbol):
    yf_symbol = map_symbol(raw_symbol)
    try:
        ticker = yf.Ticker(yf_symbol)
        
        price_data = get_price(ticker, yf_symbol)
        if price_data is None:
            return raw_symbol, {'error': 'No price found'}
            
        price, is_stale = price_data
            
        hv = calculate_hv(ticker, yf_symbol)
        iv = get_current_iv(ticker, price, yf_symbol)
        earnings_date = get_earnings_date(ticker, yf_symbol)
        
        data = {
            'price': price,
            'is_stale': is_stale,
            'hv100': hv,
            'iv30': iv,
            'earnings_date': earnings_date
        }
        
        if hv and iv:
            data['vol_bias'] = iv / hv
        
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
