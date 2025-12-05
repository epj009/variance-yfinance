import sys
import csv
from datetime import datetime
from get_market_data import get_market_data

WATCHLIST_PATH = 'watchlists/tasty-default.csv'

def get_days_to_date(date_str):
    if not date_str:
        return 999
    try:
        target = datetime.fromisoformat(date_str).date()
        today = datetime.now().date()
        delta = (target - today).days
        return delta
    except:
        return 999

def screen_volatility(limit=None):
    # 1. Read Watchlist
    symbols = []
    try:
        with open(WATCHLIST_PATH, 'r') as f:
            # Simple parsing: Skip header if exists, read first column
            reader = csv.reader(f)
            for row in reader:
                if row and row[0] != 'Symbol':
                    symbols.append(row[0])
    except Exception as e:
        print(f"Error reading watchlist: {e}")
        return

    if limit:
        symbols = symbols[:limit]
        
    print(f"Scanning {len(symbols)} symbols from {WATCHLIST_PATH}...")
    
    # 2. Get Market Data (Threaded)
    data = get_market_data(symbols)
    
    # 3. Process & Filter
    candidates = []
    for sym, metrics in data.items():
        if 'error' in metrics:
            continue
        
        iv30 = metrics.get('iv30')
        hv100 = metrics.get('hv100')
        vol_bias = metrics.get('vol_bias')
        price = metrics.get('price')
        earnings_date = metrics.get('earnings_date')
        
        days_to_earnings = get_days_to_date(earnings_date)
        
        if vol_bias is not None:
            candidates.append({
                'Symbol': sym,
                'Price': price,
                'IV30': iv30,
                'HV100': hv100,
                'Vol Bias': vol_bias,
                'Earnings In': days_to_earnings
            })
    
    # 4. Sort by Vol Bias (Descending)
    candidates.sort(key=lambda x: x['Vol Bias'], reverse=True)
    
    # 5. Print Report
    print(f"\n### 🔬 Vol Screener Report (Top Candidates)")
    print(f"**Filter:** Vol Bias (IV / HV) > 0.85 Preferred\n")
    print("| Symbol | Price | IV30 | HV100 | Vol Bias | Earn | Status |")
    print("|---|---|---|---|---|---|---|")
    
    for c in candidates:
        bias = c['Vol Bias']
        dte = c['Earnings In']
        
        status_icons = []
        
        if bias > 1.0: status_icons.append("🔥 Expensive")
        elif bias > 0.85: status_icons.append("✨ Fair/High")
        else: status_icons.append("❄️ Cheap")
        
        earn_str = "-"
        if dte < 999:
            earn_str = f"{dte}d"
            if dte <= 5 and dte >= 0:
                status_icons.append("⚠️ Earn")
        
        status = " ".join(status_icons)
        
        # Only show interesting ones or top 10
        print(f"| {c['Symbol']} | ${c['Price']:.2f} | {c['IV30']:.1f}% | {c['HV100']:.1f}% | {c['Vol Bias']:.2f} | {earn_str} | {status} |")

if __name__ == "__main__":
    limit = None
    if len(sys.argv) > 1:
        try:
            limit = int(sys.argv[1])
        except:
            pass
    screen_volatility(limit)