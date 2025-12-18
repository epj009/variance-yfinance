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
    from .config_loader import load_trading_rules, load_system_config
except ImportError:
    # Fallback for direct script execution
    from common import map_sector_to_asset_class, warn_if_not_venv
    from config_loader import load_trading_rules, load_system_config

# Load Configurations
RULES = load_trading_rules()
SYS_CONFIG = load_system_config()

try:
    with open('config/market_config.json', 'r') as f:
        MARKET_CONFIG = json.load(f)
        FAMILY_MAP = MARKET_CONFIG.get('FAMILY_MAP', {})
except Exception:
    FAMILY_MAP = {}

WATCHLIST_PATH = SYS_CONFIG.get('watchlist_path', 'watchlists/default-watchlist.csv')
FALLBACK_SYMBOLS = SYS_CONFIG.get('fallback_symbols', ['SPY', 'QQQ', 'IWM'])

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

def _is_illiquid(symbol: str, metrics: Dict[str, Any], rules: Dict[str, Any]) -> bool:
    """Checks if a symbol fails the liquidity rules."""
    # Futures exemption: Yahoo data for futures options volume is unreliable
    # Assume major futures are liquid enough or rely on user discretion
    if symbol.startswith('/'):
        return False

    # Read from flat structure (not nested)
    atm_volume = metrics.get('atm_volume')
    bid = metrics.get('atm_bid')
    ask = metrics.get('atm_ask')

    if atm_volume is not None and atm_volume < rules['min_atm_volume']:
        return True

    if bid is not None and ask is not None:
        mid = (bid + ask) / 2
        if mid > 0:
            slippage_pct = (ask - bid) / mid
            if slippage_pct > rules['max_slippage_pct']:
                return True
    return False

def _create_candidate_flags(vol_bias: Optional[float], days_to_earnings: Union[int, str], compression_ratio: Optional[float], nvrp: Optional[float], rules: Dict[str, Any]) -> Dict[str, bool]:
    """Creates a dictionary of boolean flags for a candidate."""
    return {
        'is_rich': bool(vol_bias is not None and vol_bias > rules.get('vol_bias_rich_threshold', 1.0)),
        'is_fair': bool(vol_bias is not None and rules['vol_bias_threshold'] < vol_bias <= rules.get('vol_bias_rich_threshold', 1.0)),
        'is_earnings_soon': bool(isinstance(days_to_earnings, int) and 0 <= days_to_earnings <= rules['earnings_days_threshold']),
        'is_coiled': bool(compression_ratio is not None and compression_ratio < rules.get('compression_coiled_threshold', 0.5)),
        'is_expanding': bool(compression_ratio is not None and compression_ratio > rules.get('compression_expanding_threshold', 1.0)),
        'is_cheap': bool(nvrp is not None and nvrp < rules.get('nvrp_cheap_threshold', -0.10))
    }

def _determine_signal_type(flags: Dict[str, bool], nvrp: Optional[float], rules: Dict[str, Any]) -> str:
    """
    Synthesizes multiple metrics into a single 'Signal Type' for the TUI.
    Hierarchy: EVENT > DISCOUNT > COILED > RICH > FAIR
    """
    if flags['is_earnings_soon']:
        return "EVENT"
    
    if flags.get('is_cheap'): # NVRP < -10%
        return "DISCOUNT"
        
    if flags['is_coiled']: # Ratio < 0.75
        return "BOUND"
        
    # Rich Logic: Not coiled, but high markup
    # If NVRP > 20% (0.20)
    if nvrp is not None and nvrp > 0.20:
        return "RICH"
        
    return "FAIR"

def _get_recommended_environment(signal_type: str) -> str:
    """Maps Signal Type to a recommended market environment for strategy selection."""
    if signal_type == "BOUND":
        return "High IV / Neutral (Defined)"
    elif signal_type == "RICH":
        return "High IV / Neutral (Undefined)"
    elif signal_type == "DISCOUNT":
        return "Low IV / Vol Expansion"
    elif signal_type == "EVENT":
        return "Binary Risk"
    return "Neutral / Fair Value"

def _calculate_variance_score(metrics: Dict[str, Any], rules: Dict[str, Any]) -> float:
    """
    Calculates a composite 'Variance Score' (0-100) to rank trading opportunities.
    
    Weights:
    - IV Rank (Richness): 40%
    - Vol Bias (Structural Edge): 30%
    - Vol Bias 20 (Tactical Edge): 30%
    
    Penalties:
    - HV Rank Trap: -50% score if Short Vol Trap detected.
    """
    score = 0.0
    
    # 1. IV Rank Component - REMOVED
    # ivr = metrics.get('iv_rank')
    
    # 2. Vol Bias Component (Scaled) - Weight 50%
    # Target: Bias 1.5 = 100/100, Bias 1.0 = 50/100, Bias 0.5 = 0
    bias = metrics.get('vol_bias')
    if bias:
        # Scale: (Bias - 0.5) * 100. Cap at 100, Floor at 0.
        # Example: 1.2 -> (0.7) * 100 = 70
        bias_score = max(0, min(100, (bias - 0.5) * 100))
        score += bias_score * 0.50
        
    # 3. Vol Bias 20 Component (Scaled) - Weight 50%
    bias20 = metrics.get('vol_bias_20')
    if bias20:
        bias20_score = max(0, min(100, (bias20 - 0.5) * 100))
        score += bias20_score * 0.50
    elif bias: # Fallback to standard bias if short-term missing
        score += bias_score * 0.50

    # 4. Penalties
    # HV Rank Trap: High Bias but extremely low realized vol (Dead stock with wide spreads?)
    hv_rank = metrics.get('hv_rank')
    trap_threshold = rules.get('hv_rank_trap_threshold', 15.0)
    rich_threshold = rules.get('vol_bias_rich_threshold', 1.0)
    
    if bias and bias > rich_threshold and hv_rank is not None and hv_rank < trap_threshold:
        score *= 0.50 # Slash score by half for traps
        
    return round(score, 1)

def screen_volatility(
    limit: Optional[int] = None,
    show_all: bool = False,
    show_illiquid: bool = False,
    exclude_sectors: Optional[List[str]] = None,
    include_asset_classes: Optional[List[str]] = None,
    exclude_asset_classes: Optional[List[str]] = None,
    exclude_symbols: Optional[List[str]] = None,
    held_symbols: Optional[List[str]] = None
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
    excluded_symbols_skipped = 0
    hv_rank_trap_skipped = 0  # Short vol trap filter
    low_iv_rank_skipped = 0   # Low IV Rank filter (three-factor filter)
    bats_zone_count = 0 # Initialize bats zone counter
    exclude_symbols_set = set(s.upper() for s in exclude_symbols) if exclude_symbols else set()
    
    # Expand held symbols using Family Map
    raw_held_set = set(s.upper() for s in held_symbols) if held_symbols else set()
    held_symbols_set = set(raw_held_set)
    
    # "Lineage Check": If we hold one member of a family, we effectively hold them all for screening purposes
    for family_name, siblings in FAMILY_MAP.items():
        siblings_upper = [s.upper() for s in siblings]
        # If any sibling is in our raw held list
        if not raw_held_set.isdisjoint(siblings_upper):
            # Add all siblings to the "held" set (e.g., if SLV is held, add /SI, SIVR to held set)
            held_symbols_set.update(siblings_upper)

    for sym, metrics in data.items():
        if 'error' in metrics:
            continue

        if exclude_symbols_set and sym.upper() in exclude_symbols_set:
            excluded_symbols_skipped += 1
            continue

        iv30 = metrics.get('iv')
        hv252 = metrics.get('hv252')
        hv20 = metrics.get('hv20')
        vol_bias = metrics.get('vol_bias')
        price = metrics.get('price')
        earnings_date = metrics.get('earnings_date')
        sector = metrics.get('sector', 'Unknown')

        compression_ratio = None
        if hv20 and hv252 and hv252 > 0:
            compression_ratio = hv20 / hv252

        # NVRP Calculation (Tactical Markup)
        nvrp = None
        if hv20 and hv20 > 0 and iv30:
            nvrp = (iv30 - hv20) / hv20

        # Refactored liquidity check
        is_illiquid = _is_illiquid(sym, metrics, RULES)

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

        # HV Rank Trap Detection: Filter short vol traps (high Vol Bias in dead volatility regimes)
        hv_rank = metrics.get('hv_rank')
        rich_threshold = RULES.get('vol_bias_rich_threshold', 1.0)
        trap_threshold = RULES.get('hv_rank_trap_threshold', 15.0)

        is_hv_rank_trap = (
            vol_bias is not None and
            vol_bias > rich_threshold and
            hv_rank is not None and
            hv_rank < trap_threshold
        )

        if is_hv_rank_trap and not show_all:
            hv_rank_trap_skipped += 1
            continue

        # IV Rank Filter - REMOVED
        # iv_rank = metrics.get('iv_rank')
        # iv_rank_threshold = RULES.get('iv_rank_threshold', 30.0)

        # if iv_rank is not None and iv_rank < iv_rank_threshold and not show_all:
        #    low_iv_rank_skipped += 1
        #    continue

        if is_illiquid and not show_illiquid:
            illiquid_skipped += 1
            continue

        is_bats_efficient = bool(
            price
            and vol_bias is not None
            and RULES['bats_efficiency_min_price'] <= price <= RULES['bats_efficiency_max_price']
            and vol_bias > RULES['bats_efficiency_vol_bias']
        )
        if is_bats_efficient:
            bats_zone_count += 1

        # Refactored flag creation
        flags = _create_candidate_flags(vol_bias, days_to_earnings, compression_ratio, nvrp, RULES)
        
        # Determine Signal Type
        signal_type = _determine_signal_type(flags, nvrp, RULES)
        
        # Determine Recommended Environment
        env_idea = _get_recommended_environment(signal_type)
        
        # Calculate Variance Score
        variance_score = _calculate_variance_score(metrics, RULES)
        
        # Prepare candidate data for return
        candidate_data = {
            'Symbol': sym,
            'Price': price,
            'IV30': iv30,
            'HV252': hv252,
            'HV20': hv20,
            'Compression Ratio': compression_ratio,
            'Vol Bias': vol_bias,
            'Vol Bias 20': metrics.get('vol_bias_20'), # Add Vol Bias 20 here
            'NVRP': nvrp,
            'Score': variance_score, # The Golden Metric
            'Signal': signal_type,
            'Environment': env_idea,
            'Earnings In': days_to_earnings,
            'Proxy': metrics.get('proxy'),
            'Sector': sector, # Include sector in candidate data for JSON output
            'Asset Class': asset_class, # Include asset class in candidate data for JSON output
            'is_illiquid': is_illiquid,
            'is_earnings_soon': flags['is_earnings_soon'],
            'is_bats_efficient': is_bats_efficient,
            'is_held': bool(sym.upper() in held_symbols_set)
        }
        candidate_data.update(flags)
        candidates_with_status.append(candidate_data)
    
    # 4. Sort by signal quality: NVRP (Desc), then Variance Score (Desc), then Proxy bias last
    def _signal_key(c):
        # Sorting Logic:
        # 1. Primary Key: NVRP (Descending). Fattest premium markup over movement.
        # 2. Secondary Key: Variance Score (Descending). Structural edge.
        # 3. Tertiary Key: Data Quality (0=Real, 1=Proxy). Lower is better.
        score = c['Score']
        nvrp = c.get('NVRP') or -9.9 # Default to low if missing
        proxy = c.get('Proxy')
        quality = 1 if proxy else 0
        return (nvrp, score, -quality) # Sort by NVRP DESC, then Score DESC, then Quality ASC
        
    candidates_with_status.sort(key=_signal_key, reverse=True)
    
    bias_note = "All symbols (no bias filter)" if show_all else f"Vol Bias (IV / HV) > {RULES['vol_bias_threshold']}"
    liquidity_note = "Illiquid included" if show_illiquid else f"Illiquid filtered (ATM vol < {RULES['min_atm_volume']}, slippage > {RULES['max_slippage_pct']*100:.1f}%)"

    summary = {
        "scanned_symbols_count": len(symbols),
        "low_bias_skipped_count": low_bias_skipped,
        "sector_skipped_count": sector_skipped,
        "asset_class_skipped_count": asset_class_skipped,
        "missing_bias_count": missing_bias,
        "illiquid_skipped_count": illiquid_skipped,
        "excluded_symbols_skipped_count": excluded_symbols_skipped,
        "hv_rank_trap_skipped_count": hv_rank_trap_skipped,
        "low_iv_rank_skipped_count": low_iv_rank_skipped,
        "bats_efficiency_zone_count": bats_zone_count,
        "filter_note": f"{bias_note}; {liquidity_note}"
    }

    return {"candidates": candidates_with_status, "summary": summary}

def get_screener_results(
    exclude_symbols: Optional[List[str]] = None,
    held_symbols: Optional[List[str]] = None,
    min_vol_bias: float = 0.85,
    limit: int = 20,
    filter_illiquid: bool = True,
    exclude_sectors: Optional[List[str]] = None,
    include_asset_classes: Optional[List[str]] = None,
    exclude_asset_classes: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Convenience wrapper for screen_volatility with sensible defaults.
    Used by analyze_portfolio.py for position-aware screening.

    Args:
        exclude_symbols: List of symbols to exclude from the scan.
        held_symbols: List of symbols currently held in the portfolio.
        min_vol_bias: Minimum Vol Bias threshold for candidates.
        limit: Maximum number of candidates to return.
        filter_illiquid: If True, illiquid symbols are filtered out.
        exclude_sectors: List of sector names to hide from results.
        include_asset_classes: Only show these asset classes.
        exclude_asset_classes: Hide these asset classes.

    Returns:
        Dict with 'candidates' (list of opportunities) and 'summary' (scan metadata)
    """
    return screen_volatility(
        limit=limit,
        show_all=(min_vol_bias <= 0),  # If min_vol_bias is 0 or negative, show all
        show_illiquid=(not filter_illiquid),
        exclude_symbols=exclude_symbols,
        held_symbols=held_symbols,
        exclude_sectors=exclude_sectors,
        include_asset_classes=include_asset_classes,
        exclude_asset_classes=exclude_asset_classes
    )

if __name__ == "__main__":
    warn_if_not_venv()

    parser = argparse.ArgumentParser(description='Screen for high volatility opportunities.')
    parser.add_argument('limit', type=int, nargs='?', help='Limit the number of symbols to scan (optional)')
    parser.add_argument('--show-all', action='store_true', help='Show all symbols regardless of Vol Bias')
    parser.add_argument('--show-illiquid', action='store_true', help='Include illiquid symbols (low volume or wide spreads)')
    parser.add_argument('--exclude-sectors', type=str, help='Comma-separated list of sectors to exclude (e.g., "Financial Services,Technology")')
    parser.add_argument('--include-asset-classes', type=str, help='Comma-separated list of asset classes to include (e.g., "Commodity,FX"). Options: Equity, Commodity, Fixed Income, FX, Index')
    parser.add_argument('--exclude-asset-classes', type=str, help='Comma-separated list of asset classes to exclude (e.g., "Equity"). Options: Equity, Commodity, Fixed Income, FX, Index')
    parser.add_argument('--exclude-symbols', type=str, help='Comma-separated list of symbols to exclude (e.g., "NVDA,TSLA,AMD")')
    parser.add_argument('--held-symbols', type=str, help='Comma-separated list of symbols currently in portfolio (will be flagged as held, not excluded)')

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

    exclude_symbols_list = None
    if args.exclude_symbols:
        exclude_symbols_list = [s.strip().upper() for s in args.exclude_symbols.split(',') if s.strip()]

    held_symbols_list = None
    if args.held_symbols:
        held_symbols_list = [s.strip().upper() for s in args.held_symbols.split(',') if s.strip()]

    report_data = screen_volatility(
        limit=args.limit,
        show_all=args.show_all,
        show_illiquid=args.show_illiquid,
        exclude_sectors=exclude_list,
        include_asset_classes=include_assets,
        exclude_asset_classes=exclude_assets,
        exclude_symbols=exclude_symbols_list,
        held_symbols=held_symbols_list
    )
    
    if "error" in report_data:
        print(json.dumps(report_data, indent=2))
        sys.exit(1)

    print(json.dumps(report_data, indent=2))
