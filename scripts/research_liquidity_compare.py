
import sys
import os
import json
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime
from concurrent import futures

# Add local path to import common utils if needed, though we'll likely self-contain
sys.path.append(os.getcwd())

# --- CONFIG ---
TEST_SYMBOLS = ['GLD', 'XLU', 'BAC', 'C', 'IBM', 'SNAP', 'KRE', 'KWEB', 'SPY', 'QQQ', '/ES', 'RKLB']
TARGET_DTE = 30
DTE_MIN = 25
DTE_MAX = 50
OPTION_CHAIN_LIMIT = 50
STRIKE_LOWER = 0.8
STRIKE_UPPER = 1.2

# Liquidity Rules
MIN_ATM_VOLUME = 500
MIN_ATM_OI = 500  # RFC proposed value
MAX_SLIPPAGE = 0.05

def map_symbol(symbol):
    # Minimal mapping for this test
    if symbol == '/ES': return 'ES=F'
    if symbol == '/CL': return 'CL=F'
    if symbol == '/GC': return 'GC=F'
    if symbol == '/ZN': return 'ZN=F'
    if symbol == '/6C': return 'CD=F'
    if symbol == '/6J': return 'JY=F'
    return symbol

def is_monthly_expiration(date_str):
    try:
        dt = datetime.strptime(date_str, '%Y-%m-%d').date()
        if dt.weekday() != 4: return False
        return 15 <= dt.day <= 21
    except ValueError:
        return False

def fetch_data_with_oi(raw_symbol):
    yf_symbol = map_symbol(raw_symbol)
    ticker = yf.Ticker(yf_symbol)
    
    # 1. Get Price
    try:
        current_price = ticker.fast_info.last_price
    except:
        try:
            hist = ticker.history(period="1d")
            current_price = hist['Close'].iloc[-1]
        except:
            return {'symbol': raw_symbol, 'error': 'No Price'}
            
    if not current_price:
        return {'symbol': raw_symbol, 'error': 'Zero Price'}

    # 2. Get Option Chain
    try:
        exps = ticker.options
    except:
        return {'symbol': raw_symbol, 'error': 'No Options'}
        
    if not exps:
        return {'symbol': raw_symbol, 'error': 'No Expirations'}

    today = datetime.now().date()
    monthlies_in_window = []
    weeklies_in_window = []
    
    for exp_str in exps:
        try:
            exp_date = datetime.strptime(exp_str, '%Y-%m-%d').date()
            days_out = (exp_date - today).days
            if DTE_MIN <= days_out <= DTE_MAX:
                diff = abs(days_out - TARGET_DTE)
                if is_monthly_expiration(exp_str):
                    monthlies_in_window.append((diff, exp_str))
                else:
                    weeklies_in_window.append((diff, exp_str))
        except:
            continue
            
    target_date = None
    if monthlies_in_window:
        monthlies_in_window.sort()
        target_date = monthlies_in_window[0][1]
    elif weeklies_in_window:
        weeklies_in_window.sort()
        target_date = weeklies_in_window[0][1]
        
    if not target_date:
        return {'symbol': raw_symbol, 'error': 'No Chain in Window'}
        
    # 3. Fetch Chain
    try:
        chain = ticker.option_chain(target_date)
        calls = chain.calls
        puts = chain.puts
    except Exception as e:
        return {'symbol': raw_symbol, 'error': f'Chain Fetch Fail: {str(e)}'}
        
    # 4. Find ATM
    def _prep(df):
        df = df.copy()
        df['dist'] = abs(df['strike'] - current_price)
        return df
        
    calls = _prep(calls).sort_values('dist').head(OPTION_CHAIN_LIMIT)
    puts = _prep(puts).sort_values('dist').head(OPTION_CHAIN_LIMIT)
    
    if calls.empty or puts.empty:
        return {'symbol': raw_symbol, 'error': 'Empty Chain'}
        
    atm_call = calls.iloc[0]
    atm_put = puts.iloc[0]
    
    # 5. Extract Metrics
    c_vol = float(atm_call.get('volume', 0) or 0)
    p_vol = float(atm_put.get('volume', 0) or 0)
    c_oi = float(atm_call.get('openInterest', 0) or 0)
    p_oi = float(atm_put.get('openInterest', 0) or 0)
    
    c_bid = float(atm_call.get('bid', 0) or 0)
    c_ask = float(atm_call.get('ask', 0) or 0)
    p_bid = float(atm_put.get('bid', 0) or 0)
    p_ask = float(atm_put.get('ask', 0) or 0)
    
    atm_vol_total = c_vol + p_vol
    atm_oi_total = c_oi + p_oi
    
    # Slippage Calculation
    slippage_passed = True
    c_mid = (c_bid + c_ask) / 2
    p_mid = (p_bid + p_ask) / 2
    
    c_slip = (c_ask - c_bid) / c_mid if c_mid > 0 else 1.0
    p_slip = (p_ask - p_bid) / p_mid if p_mid > 0 else 1.0
    
    if c_slip > MAX_SLIPPAGE or p_slip > MAX_SLIPPAGE:
        slippage_passed = False
        
    # Decisions
    vol_pass = atm_vol_total >= MIN_ATM_VOLUME
    oi_pass = atm_oi_total >= MIN_ATM_OI
    
    # "Dead Leg" Check (RFC Mention)
    # The RFC mentions "ensure neither leg is dead".
    # Current screener logic fails if EITHER volume is 0.
    # RFC implies we should check OI per leg too? Let's check total for now as per RFC text "sum of ATM call + ATM put OI"
    
    return {
        'symbol': raw_symbol,
        'price': current_price,
        'target_date': target_date,
        'atm_vol': atm_vol_total,
        'atm_oi': atm_oi_total,
        'vol_pass': vol_pass,
        'oi_pass': oi_pass,
        'slippage_pass': slippage_passed,
        'c_vol': c_vol,
        'p_vol': p_vol,
        'c_oi': c_oi,
        'p_oi': p_oi,
        'slippage_pct': max(c_slip, p_slip)
    }

def main():
    print(f"Running Liquidity Research on {len(TEST_SYMBOLS)} symbols...")
    print(f"Rules: Volume >= {MIN_ATM_VOLUME} | OI >= {MIN_ATM_OI} | Slippage <= {MAX_SLIPPAGE*100}%")
    print("-" * 100)
    print(f"{'SYMBOL':<8} {'PRICE':<8} {'EXP':<12} {'VOL':<8} {'OI':<8} {'SLIP%':<6} {'VOL_RES':<8} {'OI_RES':<8} {'CHANGE'}")
    print("-" * 100)
    
    results = []
    with futures.ThreadPoolExecutor() as executor:
        future_to_sym = {executor.submit(fetch_data_with_oi, sym): sym for sym in TEST_SYMBOLS}
        for future in futures.as_completed(future_to_sym):
            data = future.result()
            results.append(data)
            
    # Sort by symbol
    results.sort(key=lambda x: x['symbol'])
    
    for r in results:
        if 'error' in r:
            print(f"{r['symbol']:<8} ERROR: {r['error']}")
            continue
            
        vol_status = "PASS" if r['vol_pass'] and r['slippage_pass'] else "FAIL"
        if not r['slippage_pass']: vol_status = "SLIP"
        
        oi_status = "PASS" if r['oi_pass'] and r['slippage_pass'] else "FAIL"
        if not r['slippage_pass']: oi_status = "SLIP"
        
        # Determine delta
        change = ""
        if vol_status != "PASS" and oi_status == "PASS":
            change = "✅ GAINED"
        elif vol_status == "PASS" and oi_status != "PASS":
            change = "❌ LOST"
        elif vol_status == "PASS" and oi_status == "PASS":
            change = "➡️  KEPT"
        else:
            change = "⛔ REJECTED"
            
        print(f"{r['symbol']:<8} "
              f"{r['price']:<8.2f} "
              f"{r['target_date']:<12} "
              f"{r['atm_vol']:<8.0f} "
              f"{r['atm_oi']:<8.0f} "
              f"{r['slippage_pct']*100:<6.1f} "
              f"{vol_status:<8} "
              f"{oi_status:<8} "
              f"{change}")

if __name__ == "__main__":
    main()
