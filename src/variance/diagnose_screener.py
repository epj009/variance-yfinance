
import sys
import json
import csv
from datetime import datetime
from collections import defaultdict
from vol_screener import load_profile_config, screen_volatility, _is_illiquid
from get_market_data import MarketDataFactory
from config_loader import load_config_bundle

def diagnose_watchlist():
    """
    Diagnoses the entire watchlist to categorize why symbols are dropped.
    """
    print("--- Diagnosing Full Watchlist ---")

    # 1. Load Config & Watchlist
    config_bundle = load_config_bundle()
    rules = config_bundle['trading_rules']
    watchlist_path = config_bundle['system_config'].get('watchlist_path', 'watchlists/default-watchlist.csv')
    
    symbols = []
    try:
        with open(watchlist_path, 'r') as f:
            reader = csv.reader(f)
            for row in reader:
                if row and row[0] != 'Symbol':
                    symbols.append(row[0])
    except Exception as e:
        print(f"❌ Error reading watchlist: {e}")
        return

    print(f"1. Fetching Market Data for {len(symbols)} symbols...")
    provider = MarketDataFactory.get_provider()
    market_data = provider.get_market_data(symbols)
    
    # Trackers
    stats = defaultdict(list)
    passed = []
    
    for sym in symbols:
        if sym not in market_data:
            stats["DATA_FETCH_ERROR"].append(sym)
            continue
            
        data = market_data[sym]
        if 'error' in data:
            stats[f"API_ERROR_{data['error']}"].append(sym)
            continue

        # --- Filter Logic (Replicating vol_screener.py) ---
        dropped = False
        
        # 1. Liquidity
        is_illiquid = _is_illiquid(sym, data, rules)
        if is_illiquid:
             # Gather details for the report
             vol = data.get('atm_volume', 0)
             oi = data.get('atm_open_interest', 0)
             
             # Calculate max slippage from legs for diagnostics
             max_slip = 0.0
             legs = [
                ('C', data.get('call_bid'), data.get('call_ask')),
                ('P', data.get('put_bid'), data.get('put_ask'))
             ]
             for side, bid, ask in legs:
                 if bid is not None and ask is not None:
                     mid = (bid + ask) / 2
                     if mid > 0:
                         slip = (ask - bid) / mid
                         if slip > max_slip: max_slip = slip
             
             stats["ILLIQUID"].append(f"{sym} (Vol:{vol} | OI:{oi} | Slip:{max_slip:.1%})")
             dropped = True
        
        # 2. VRP Structural (Bias)
        vrp_s = data.get('vrp_structural')
        threshold = rules.get('vrp_structural_threshold', 0.85)
        
        if vrp_s is None:
            stats["MISSING_METRICS"].append(sym)
            dropped = True
        elif vrp_s <= threshold:
            stats["LOW_VRP_STRUCTURAL"].append(f"{sym} ({vrp_s:.2f})")
            dropped = True

        # 3. Low Vol Trap (Absolute)
        hv252 = data.get('hv252')
        hv_floor = rules.get('hv_floor_percent', 5.0)
        if hv252 is not None and hv252 < hv_floor:
             stats["LOW_VOL_TRAP"].append(f"{sym} (HV: {hv252:.1f})")
             dropped = True
        
        # 4. HV Rank Trap (Relative)
        hv_rank = data.get('hv_rank')
        trap_thresh = rules.get('hv_rank_trap_threshold', 15.0)
        rich_thresh = rules.get('vrp_structural_rich_threshold', 1.0)
        
        if vrp_s and vrp_s > rich_thresh and hv_rank is not None and hv_rank < trap_thresh:
            stats["HV_RANK_TRAP"].append(f"{sym} (Rank: {hv_rank:.1f})")
            dropped = True
            
        # 5. Data Integrity
        if data.get('warning'):
             stats["DATA_INTEGRITY"].append(f"{sym}: {data['warning']}")
             dropped = True

        if not dropped:
            passed.append(sym)

    # --- Report ---
    print("\n" + "="*40)
    print("      SCREENER DIAGNOSTIC REPORT")
    print("="*40)
    
    print(f"\n✅ PASSED ({len(passed)}): {', '.join(passed[:10])}{'...' if len(passed)>10 else ''}")
    
    print(f"\n❌ DROPPED ({len(symbols) - len(passed)}):")
    for reason, items in sorted(stats.items()):
        print(f"\n  • {reason} ({len(items)}):")
        # Show first 5 and last 5 if list is long
        if len(items) > 10:
             display = items[:5] + ["..."] + items[-5:]
        else:
             display = items
        for item in display:
            print(f"    - {item}")

if __name__ == "__main__":
    diagnose_watchlist()
