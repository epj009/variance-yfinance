import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import math

# Pure Python Normal CDF (Error Function approximation)
def norm_cdf(x):
    return (1.0 + math.erf(x / math.sqrt(2.0))) / 2.0

# --- CONFIG ---
SYMBOLS = ['BAC', 'QCOM', 'AMZN', 'GLD', 'SLV', 'TGT', 'MS', 'META']
TARGET_DTE = 45
RISK_FREE_RATE = 0.045

print(f"🔬 VARIANCE RESEARCH: Mechanics Impact Study")
print(f"   Target Strategy: Jade Lizard (30 Delta Put / 30 Delta Call Spread)")
print(f"   Hypothesis: Low-priced stocks will fail the 'Credit > Width' rule.")
print("-" * 80)
print(f"{'SYMBOL':<8} {'PRICE':<8} {'IV':<6} {'PUT($)':<8} {'CALL($)':<8} {'WIDTH':<6} {'CREDIT':<8} {'SCORE':<6} {'STATUS'}")
print("-" * 80)

def black_scholes_delta(S, K, T, r, sigma, option_type='call'):
    """Estimate Delta to find strikes."""
    if T <= 0 or sigma <= 0: return 0.5
    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    if option_type == 'call':
        return norm_cdf(d1)
    else:
        return -norm_cdf(-d1)

def find_strike_by_delta(chain, S, T, r, sigma, target_delta, option_type='call'):
    """Find the strike closest to target delta."""
    # Add Delta column
    chain['delta_est'] = chain['strike'].apply(
        lambda k: black_scholes_delta(S, k, T, r, sigma, option_type)
    )
    # Find closest
    chain['delta_dist'] = abs(chain['delta_est'] - target_delta)
    best_fit = chain.sort_values('delta_dist').iloc[0]
    return best_fit

for symbol in SYMBOLS:
    try:
        ticker = yf.Ticker(symbol)
        
        # 1. Get Price
        try:
            price = ticker.fast_info.last_price
        except:
            hist = ticker.history(period='1d')
            price = hist['Close'].iloc[-1]
            
        # 2. Find Expiration
        exps = ticker.options
        today = datetime.now().date()
        target_date_str = None
        min_diff = 999
        
        for exp in exps:
            exp_date = datetime.strptime(exp, '%Y-%m-%d').date()
            days = (exp_date - today).days
            diff = abs(days - TARGET_DTE)
            if diff < min_diff and days > 25:
                min_diff = diff
                target_date_str = exp
                
        if not target_date_str:
            print(f"{symbol:<8} NO EXPIRATION FOUND")
            continue
            
        T = (datetime.strptime(target_date_str, '%Y-%m-%d').date() - today).days / 365.0
        
        # 3. Get Chain & Estimate IV (using ATM)
        chain = ticker.option_chain(target_date_str)
        calls = chain.calls
        puts = chain.puts
        
        # Simple ATM IV estimator
        atm_call = calls.iloc[(calls['strike'] - price).abs().argsort()[:1]]
        iv = atm_call['impliedVolatility'].values[0]
        
        if pd.isna(iv) or iv == 0:
            iv = 0.3 # Fallback
            
        # 4. Mechanics: Build the Lizard
        # Leg 1: Sell 30 Delta Put
        short_put = find_strike_by_delta(puts, price, T, RISK_FREE_RATE, iv, -0.30, 'put')
        put_credit = (short_put['bid'] + short_put['ask']) / 2
        
        # Leg 2: Sell 30 Delta Call Spread
        short_call = find_strike_by_delta(calls, price, T, RISK_FREE_RATE, iv, 0.30, 'call')
        
        # Find Long Call (Width Logic)
        # Try to find a width that is roughly 2.5, 5, or 10 depending on price
        ideal_width = 2.5 if price < 100 else 5.0
        long_strike_target = short_call['strike'] + ideal_width
        
        # Snap to real strike
        long_call = calls.iloc[(calls['strike'] - long_strike_target).abs().argsort()[:1]].iloc[0]
        real_width = long_call['strike'] - short_call['strike']
        
        call_credit_gross = (short_call['bid'] + short_call['ask']) / 2
        call_debit_gross = (long_call['bid'] + long_call['ask']) / 2
        call_spread_net = call_credit_gross - call_debit_gross
        
        total_credit = put_credit + call_spread_net
        
        # The Score: Credit / Width
        # > 1.0 means Risk Free Upside
        score = total_credit / real_width if real_width > 0 else 0
        
        status = "✅ PASS" if score >= 1.0 else "❌ FAIL"
        if 0.85 <= score < 1.0: status = "⚠️ WARN"
        
        print(f"{symbol:<8} ${price:<7.2f} {iv*100:.0f}%   {short_put['strike']:<8} {short_call['strike']}/{long_call['strike']:<8} ${real_width:<5.2f} ${total_credit:<7.2f} {score:<6.2f} {status}")

    except Exception as e:
        print(f"{symbol:<8} ERROR: {str(e)}")
