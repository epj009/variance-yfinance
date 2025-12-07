import sys
import csv
import json
import argparse
from datetime import datetime
from get_market_data import get_market_data

# Default to the broader house list
WATCHLIST_PATH = 'watchlists/default-watchlist.csv'

# Load Trading Rules
try:
    with open('config/trading_rules.json', 'r') as f:
        RULES = json.load(f)
except FileNotFoundError:
    print("Warning: config/trading_rules.json not found. Using defaults.", file=sys.stderr)
    RULES = {
        "vol_bias_threshold": 0.85,
        "earnings_days_threshold": 5
    }

def get_days_to_date(date_str):
    """Calculate the number of days from today until the given date string (ISO format)."""
    if not date_str or date_str == "Unavailable":
        return "N/A" # Return a string for unavailable
    try:
        target = datetime.fromisoformat(date_str).date()
        today = datetime.now().date()
        delta = (target - today).days
        return delta
    except:
        return "N/A"

def screen_volatility(limit=None, show_all=False, exclude_sectors=None):
    """
    Scan the watchlist for high-volatility trading opportunities.
    
    Fetches market data, filters by Vol Bias threshold (unless show_all=True),
    and optionally excludes specific sectors. Prints a formatted report.
    
    Args:
        limit (int, optional): Max number of symbols to scan.
        show_all (bool): If True, displays all symbols regardless of Vol Bias.
        exclude_sectors (list[str], optional): List of sector names to hide from results.
    """
    # 1. Read Watchlist
    symbols = []
    try:
        with open(WATCHLIST_PATH, 'r') as f:
            # Simple parsing: Skip header if exists, read first column
            reader = csv.reader(f)
            for row in reader:
                if row and row[0] != 'Symbol':
                    symbols.append(row[0])
    except FileNotFoundError:
        print(f"Warning: Watchlist file '{WATCHLIST_PATH}' not found. Using default symbols (SPY, QQQ, IWM).")
        symbols = ['SPY', 'QQQ', 'IWM']
    except Exception as e:
        print(f"Error reading watchlist: {e}")
        return

    if limit:
        symbols = symbols[:limit]
    
    if exclude_sectors:
        print(f"Scanning {len(symbols)} symbols from {WATCHLIST_PATH} (Excluding: {', '.join(exclude_sectors)})...")
    else:
        print(f"Scanning {len(symbols)} symbols from {WATCHLIST_PATH}...")
    
    # 2. Get Market Data (Threaded)
    data = get_market_data(symbols)
    
    # 3. Process & Filter
    candidates = []
    low_bias_skipped = 0
    missing_bias = 0
    sector_skipped = 0

    for sym, metrics in data.items():
        if 'error' in metrics:
            continue
        
        iv30 = metrics.get('iv30')
        hv252 = metrics.get('hv252')
        vol_bias = metrics.get('vol_bias')
        price = metrics.get('price')
        earnings_date = metrics.get('earnings_date')
        sector = metrics.get('sector', 'Unknown')
        
        # Sector Filter
        if exclude_sectors and sector in exclude_sectors:
            sector_skipped += 1
            continue

        days_to_earnings = get_days_to_date(earnings_date)
        
        if vol_bias is None:
            missing_bias += 1
            if not show_all:
                continue
        elif vol_bias <= RULES['vol_bias_threshold'] and not show_all:
            low_bias_skipped += 1
            continue

        candidates.append({
            'Symbol': sym,
            'Price': price,
            'IV30': iv30,
            'HV252': hv252,
            'Vol Bias': vol_bias,
            'Earnings In': days_to_earnings,
            'Proxy': metrics.get('proxy')
        })
    
    # 4. Sort by signal quality: real bias first, proxy bias second, no-bias last; then bias desc within group
    def _signal_key(c):
        # Sorting Logic:
        # 1. Primary Key: Data Quality (0=Real Bias, 1=Proxy Bias, 2=No Bias). Lower is better.
        # 2. Secondary Key: Vol Bias (Descending). Higher is better.
        # Returns a tuple for comparison.
        bias = c['Vol Bias']
        proxy = c.get('Proxy')
        if bias is None:
            return (2, 0)
        if proxy:
            return (1, bias)
        return (0, bias)
    candidates.sort(key=lambda c: (_signal_key(c)[0], -_signal_key(c)[1]))
    
    # 5. Print Report
    print(f"\n### 🔬 Vol Screener Report (Top Candidates)")
    filter_note = "All symbols (no bias filter)" if show_all else f"Vol Bias (IV / HV) > {RULES['vol_bias_threshold']}"
    print(f"**Filter:** {filter_note}\n")
    print("| Symbol | Price | IV30 | HV252 | Vol Bias | Earn | Status |")
    print("|---|---|---|---|---|---|---|")
    
    for c in candidates:
        bias = c['Vol Bias']
        dte = c['Earnings In']
        proxy_note = c.get('Proxy')
        
        status_icons = []
        
        if bias is None:
            status_icons.append("❓ No Bias")
        elif bias > 1.0:
            status_icons.append("🔥 Expensive")
        elif bias > RULES['vol_bias_threshold']:
            status_icons.append("✨ Fair/High")
        else:
            status_icons.append("❄️ Cheap")
        
        earn_str = dte # Direct assignment now
        if isinstance(dte, int) and dte <= RULES['earnings_days_threshold'] and dte >= 0:
            status_icons.append("⚠️ Earn")
        
        status = " ".join(status_icons)

        price_str = f"${c['Price']:.2f}" if c['Price'] is not None else "N/A"
        iv_str = f"{c['IV30']:.1f}%" if c['IV30'] is not None else "N/A"
        hv_str = f"{c['HV252']:.1f}%" if c['HV252'] is not None else "N/A"
        bias_str = f"{bias:.2f}" if bias is not None else "N/A"
        
        note = f" ({proxy_note})" if proxy_note else ""
        
        # Only show interesting ones or top 10
        print(f"| {c['Symbol']}{note} | {price_str} | {iv_str} | {hv_str} | {bias_str} | {earn_str} | {status} |")

    # Summary of filtered symbols
    if not show_all:
        print(f"\nSkipped {low_bias_skipped} symbols below bias threshold, {sector_skipped} excluded by sector, and {missing_bias} with missing bias.")
    elif missing_bias:
        print(f"\nNote: {missing_bias} symbols missing bias (no IV/HV).")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Screen for high volatility opportunities.')
    parser.add_argument('limit', type=int, nargs='?', help='Limit the number of symbols to scan (optional)')
    parser.add_argument('--show-all', action='store_true', help='Show all symbols regardless of Vol Bias')
    parser.add_argument('--exclude-sectors', type=str, help='Comma-separated list of sectors to exclude (e.g., "Financial Services,Technology")')
    
    args = parser.parse_args()
    
    exclude_list = None
    if args.exclude_sectors:
        exclude_list = [s.strip() for s in args.exclude_sectors.split(',')]

    screen_volatility(limit=args.limit, show_all=args.show_all, exclude_sectors=exclude_list)
