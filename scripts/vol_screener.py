import argparse
import csv
import json
import sys
from datetime import datetime
from typing import Dict, List, Optional, Any, Union

from get_market_data import get_market_data

# Import common utilities
try:
    from .common import map_sector_to_asset_class, warn_if_not_venv
except ImportError:
    # Fallback for direct script execution
    from common import map_sector_to_asset_class, warn_if_not_venv

# Baseline trading rules to ensure CLI remains usable even if config is missing
RULES_DEFAULT = {
    "vol_bias_threshold": 0.85,
    "earnings_days_threshold": 5,
    "bats_efficiency_min_price": 15,
    "bats_efficiency_max_price": 75,
    "bats_efficiency_vol_bias": 1.0,
}

MIN_ATM_VOLUME = 500
MAX_SLIPPAGE_PCT = 0.05

# Load System Config
try:
    with open('config/system_config.json', 'r') as f:
        SYS_CONFIG = json.load(f)
    WATCHLIST_PATH = SYS_CONFIG.get('watchlist_path', 'watchlists/default-watchlist.csv')
    FALLBACK_SYMBOLS = SYS_CONFIG.get('fallback_symbols', ['SPY', 'QQQ', 'IWM'])
except FileNotFoundError:
    print("Warning: config/system_config.json not found. Using defaults.", file=sys.stderr)
    WATCHLIST_PATH = 'watchlists/default-watchlist.csv'
    FALLBACK_SYMBOLS = ['SPY', 'QQQ', 'IWM']

# Load Trading Rules
try:
    with open('config/trading_rules.json', 'r') as f:
        RULES = {**RULES_DEFAULT, **json.load(f)}
except FileNotFoundError:
    print("Warning: config/trading_rules.json not found. Using defaults.", file=sys.stderr)
    RULES = RULES_DEFAULT.copy()

def get_days_to_date(date_str: Optional[str]) -> Union[int, str]:
    """
    Calculate the number of days from today until the given date string (ISO format).
    
    Args:
        date_str: ISO format date string or "Unavailable".
        
    Returns:
        Number of days as integer, or "N/A" if date is unavailable or invalid.
    """
    if not date_str or date_str == "Unavailable":
        return "N/A"  # Return a string for unavailable
    try:
        target = datetime.fromisoformat(date_str).date()
        today = datetime.now().date()
        delta = (target - today).days
        return delta
    except (ValueError, TypeError):
        return "N/A"

def screen_volatility(
    limit: Optional[int] = None,
    show_all: bool = False,
    show_illiquid: bool = False,
    exclude_sectors: Optional[List[str]] = None,
    include_asset_classes: Optional[List[str]] = None,
    exclude_asset_classes: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Scan the watchlist for high-volatility trading opportunities.

    Fetches market data, filters by Vol Bias threshold (unless show_all=True), filters out illiquid names
    (unless show_illiquid=True),
    and optionally excludes specific sectors or filters by asset class. Returns a structured report.

    Args:
        limit: Max number of symbols to scan.
        show_all: If True, displays all symbols regardless of Vol Bias.
        show_illiquid: If True, includes names that fail liquidity checks.
        exclude_sectors: List of sector names to hide from results.
        include_asset_classes: Only show these asset classes (e.g., ["Commodity", "FX"]).
        exclude_asset_classes: Hide these asset classes (e.g., ["Equity"]).

    Returns:
        A dictionary containing 'candidates' (list of dicts) and 'summary' (dict).
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
        symbols = FALLBACK_SYMBOLS
    except Exception as e:
        return {"error": f"Error reading watchlist: {e}"}

    if limit:
        symbols = symbols[:limit]
    
    # 2. Get Market Data (Threaded)
    data = get_market_data(symbols)
    
    # 3. Process & Filter
    candidates_with_status = []
    low_bias_skipped = 0
    missing_bias = 0
    sector_skipped = 0
    asset_class_skipped = 0
    illiquid_skipped = 0
    bats_zone_count = 0 # Initialize bats zone counter

    for sym, metrics in data.items():
        if 'error' in metrics:
            continue

        iv30 = metrics.get('iv30')
        hv252 = metrics.get('hv252')
        vol_bias = metrics.get('vol_bias')
        price = metrics.get('price')
        earnings_date = metrics.get('earnings_date')
        sector = metrics.get('sector', 'Unknown')
        liquidity = metrics.get('liquidity') or {}
        atm_volume = liquidity.get('atm_volume')
        bid = liquidity.get('bid')
        ask = liquidity.get('ask')

        slippage_pct = None
        if bid is not None and ask is not None:
            mid = (bid + ask) / 2
            if mid > 0:
                slippage_pct = (ask - bid) / mid

        is_illiquid = False
        if atm_volume is not None and atm_volume < MIN_ATM_VOLUME:
            is_illiquid = True
        if slippage_pct is not None and slippage_pct > MAX_SLIPPAGE_PCT:
            is_illiquid = True

        # Sector Filter
        if exclude_sectors and sector in exclude_sectors:
            sector_skipped += 1
            continue

        # Asset Class Filter
        asset_class = map_sector_to_asset_class(sector)
        if include_asset_classes and asset_class not in include_asset_classes:
            asset_class_skipped += 1
            continue
        if exclude_asset_classes and asset_class in exclude_asset_classes:
            asset_class_skipped += 1
            continue

        days_to_earnings = get_days_to_date(earnings_date)
        
        if vol_bias is None:
            missing_bias += 1
            if not show_all:
                continue
        elif vol_bias <= RULES['vol_bias_threshold'] and not show_all:
            low_bias_skipped += 1
            continue

        if is_illiquid and not show_illiquid:
            illiquid_skipped += 1
            continue

        # --- Determine Status Icons ---
        status_icons = []
        
        if vol_bias is None: # Use vol_bias here, not 'bias' from c (candidate)
            status_icons.append("❓ No Bias")
        elif vol_bias > 1.0:
            status_icons.append("🔥 Rich")
        elif vol_bias > RULES['vol_bias_threshold']:
            status_icons.append("✨ Fair/High")
        else:
            status_icons.append("❄️ Low")

        # Bat's Efficiency Zone Check
        if price and RULES['bats_efficiency_min_price'] <= price <= RULES['bats_efficiency_max_price'] and vol_bias > RULES['bats_efficiency_vol_bias']:
            status_icons.append("🦇 Bat's Efficiency Zone")
            bats_zone_count += 1
        
        if isinstance(days_to_earnings, int) and days_to_earnings <= RULES['earnings_days_threshold'] and days_to_earnings >= 0:
            status_icons.append("⚠️ Earn")
        if is_illiquid:
            status_icons.append("🚱 Illiquid")
        
        # Prepare candidate data for return
        candidate_data = {
            'Symbol': sym,
            'Price': price,
            'IV30': iv30,
            'HV252': hv252,
            'Vol Bias': vol_bias,
            'Earnings In': days_to_earnings,
            'Proxy': metrics.get('proxy'),
            'Status Icons': status_icons, # Raw icons for JSON, will be joined for Markdown
            'Sector': sector, # Include sector in candidate data for JSON output
            'Asset Class': asset_class # Include asset class in candidate data for JSON output
        }
        candidates_with_status.append(candidate_data)
    
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
    candidates_with_status.sort(key=lambda c: (_signal_key(c)[0], -_signal_key(c)[1]))
    
    bias_note = "All symbols (no bias filter)" if show_all else f"Vol Bias (IV / HV) > {RULES['vol_bias_threshold']}"
    liquidity_note = "Illiquid included" if show_illiquid else f"Illiquid filtered (ATM vol < {MIN_ATM_VOLUME}, slippage > {MAX_SLIPPAGE_PCT*100:.1f}%)"

    summary = {
        "scanned_symbols_count": len(symbols),
        "low_bias_skipped_count": low_bias_skipped,
        "sector_skipped_count": sector_skipped,
        "asset_class_skipped_count": asset_class_skipped,
        "missing_bias_count": missing_bias,
        "illiquid_skipped_count": illiquid_skipped,
        "bats_efficiency_zone_count": bats_zone_count,
        "filter_note": f"{bias_note}; {liquidity_note}"
    }

    return {"candidates": candidates_with_status, "summary": summary}

if __name__ == "__main__":
    warn_if_not_venv()

    parser = argparse.ArgumentParser(description='Screen for high volatility opportunities.')
    parser.add_argument('limit', type=int, nargs='?', help='Limit the number of symbols to scan (optional)')
    parser.add_argument('--show-all', action='store_true', help='Show all symbols regardless of Vol Bias')
    parser.add_argument('--show-illiquid', action='store_true', help='Include illiquid symbols (low volume or wide spreads)')
    parser.add_argument('--exclude-sectors', type=str, help='Comma-separated list of sectors to exclude (e.g., "Financial Services,Technology")')
    parser.add_argument('--include-asset-classes', type=str, help='Comma-separated list of asset classes to include (e.g., "Commodity,FX"). Options: Equity, Commodity, Fixed Income, FX, Index')
    parser.add_argument('--exclude-asset-classes', type=str, help='Comma-separated list of asset classes to exclude (e.g., "Equity"). Options: Equity, Commodity, Fixed Income, FX, Index')
    parser.add_argument('--text', action='store_true', help='Output results in human-readable text format (default is JSON).')

    args = parser.parse_args()

    exclude_list = None
    if args.exclude_sectors:
        exclude_list = [s.strip() for s in args.exclude_sectors.split(',')]

    include_assets = None
    if args.include_asset_classes:
        include_assets = [s.strip() for s in args.include_asset_classes.split(',')]

    exclude_assets = None
    if args.exclude_asset_classes:
        exclude_assets = [s.strip() for s in args.exclude_asset_classes.split(',')]

    report_data = screen_volatility(
        limit=args.limit,
        show_all=args.show_all,
        show_illiquid=args.show_illiquid,
        exclude_sectors=exclude_list,
        include_asset_classes=include_assets,
        exclude_asset_classes=exclude_assets
    )
    
    if "error" in report_data:
        print(json.dumps(report_data, indent=2))
        sys.exit(1)

    if args.text:
        # --- Original Markdown Printing Logic ---
        summary = report_data['summary']
        candidates = report_data['candidates']
        
        print(f"Scanning {summary['scanned_symbols_count']} symbols from {WATCHLIST_PATH}" + (f" (Excluding: {', '.join(exclude_list)})" if exclude_list else "") + "...")
        print(f"\n### 🔬 Vol Screener Report (Top Candidates)")
        print(f"**Filter:** {summary['filter_note']}\n")
        print("| Symbol | Price | IV30 | HV252 | Vol Bias | Earn | Status |")
        print("|---|---|---|---|---|---|---|")
        
        for c in candidates:
            price_str = f"${c['Price']:.2f}" if c['Price'] is not None else "N/A"
            iv_str = f"{c['IV30']:.1f}%" if c['IV30'] is not None else "N/A"
            hv_str = f"{c['HV252']:.1f}%" if c['HV252'] is not None else "N/A"
            bias_str = f"{c['Vol Bias']:.2f}" if c['Vol Bias'] is not None else "N/A"
            
            note = f" ({c['Proxy']})" if c['Proxy'] else ""
            status = " ".join(c['Status Icons'])
            
            print(f"| {c['Symbol']}{note} | {price_str} | {iv_str} | {hv_str} | {bias_str} | {c['Earnings In']} | {status} |")

        # Summary of filtered symbols
        if not args.show_all:
            print(f"\nSkipped {summary['low_bias_skipped_count']} symbols below bias threshold, {summary['illiquid_skipped_count']} illiquid, {summary['sector_skipped_count']} excluded by sector, {summary['asset_class_skipped_count']} excluded by asset class, and {summary['missing_bias_count']} with missing bias.")
        elif summary['missing_bias_count']:
            print(f"\nNote: {summary['missing_bias_count']} symbols missing bias (no IV/HV).")

        if summary['illiquid_skipped_count'] > 0 and not args.show_illiquid:
            print(f"Filtered {summary['illiquid_skipped_count']} illiquid symbols (ATM vol < {MIN_ATM_VOLUME} or slippage > {MAX_SLIPPAGE_PCT*100:.1f}%).")

        if summary['asset_class_skipped_count'] > 0 and args.show_all:
            print(f"Filtered {summary['asset_class_skipped_count']} symbols by asset class.")
        
        # Bat's Efficiency Zone Summary
        if summary['bats_efficiency_zone_count'] > 0:
            print(f"\nFound {summary['bats_efficiency_zone_count']} symbols in the 🦇 Bat's Efficiency Zone (Price: ${RULES['bats_efficiency_min_price']}-${RULES['bats_efficiency_max_price']}, Vol Bias > {RULES['bats_efficiency_vol_bias']}).")
    else:
        print(json.dumps(report_data, indent=2))
