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
        # Use mark price if available, otherwise mid price
        mark_price = metrics.get('atm_mark')
        if mark_price:
            reference_price = float(mark_price)
        else:
            reference_price = (bid + ask) / 2

        if reference_price > 0:
            slippage_pct = (ask - bid) / reference_price
            if slippage_pct > rules['max_slippage_pct']:
                return True
    return False

def _create_candidate_flags(vrp_structural: Optional[float], days_to_earnings: Union[int, str], compression_ratio: Optional[float], nvrp: Optional[float], rules: Dict[str, Any]) -> Dict[str, bool]:
    """Creates a dictionary of boolean flags for a candidate."""
    return {
        'is_rich': bool(vrp_structural is not None and vrp_structural > rules.get('vrp_structural_rich_threshold', 1.0)),
        'is_fair': bool(vrp_structural is not None and rules['vrp_structural_threshold'] < vrp_structural <= rules.get('vrp_structural_rich_threshold', 1.0)),
        'is_earnings_soon': bool(isinstance(days_to_earnings, int) and 0 <= days_to_earnings <= rules['earnings_days_threshold']),
        'is_coiled': bool(compression_ratio is not None and compression_ratio < rules.get('compression_coiled_threshold', 0.5)),
        'is_expanding': bool(compression_ratio is not None and compression_ratio > rules.get('compression_expanding_threshold', 1.0)),
        'is_cheap': bool(nvrp is not None and nvrp < rules.get('vrp_tactical_cheap_threshold', -0.10))
    }

def _determine_signal_type(flags: Dict[str, bool], nvrp: Optional[float], rules: Dict[str, Any]) -> str:
    """
    Synthesizes multiple metrics into a single 'Signal Type' for the TUI.
    Hierarchy: EVENT > DISCOUNT > COILED > RICH > FAIR
    """
    if flags['is_earnings_soon']:
        return "EVENT"
    
    if flags.get('is_cheap'): # VRP Tactical < -10%
        return "DISCOUNT"
        
    if flags['is_coiled']: # Ratio < 0.75
        return "BOUND"
        
    # Rich Logic: Not coiled, but high markup
    # If VRP Tactical > 20% (0.20)
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
    - VRP Structural Dislocation (Structural Edge): 50%
    - VRP Tactical Dislocation (Tactical Edge): 50%
    
    The score measures the ABSOLUTE distance from Fair Value (1.0).
    Significant dislocation in either direction (Rich or Cheap) results in a high score.
    
    Penalties:
    - HV Rank Trap: -50% score if Short Vol Trap detected.
    """
    score = 0.0
    
    # 1. VRP Structural Component (Absolute Dislocation)
    # Target: |Bias - 1.0| * 200. Max 100.
    # Example: 1.5 -> 0.5 * 200 = 100. 0.5 -> 0.5 * 200 = 100.
    bias = metrics.get('vrp_structural')
    if bias:
        bias_dislocation = abs(bias - 1.0) * RULES.get('variance_score_dislocation_multiplier', 200)
        bias_score = max(0, min(100, bias_dislocation))
        score += bias_score * 0.50
        
    # 2. VRP Tactical Component (Absolute Dislocation)
    bias20 = metrics.get('vrp_tactical')
    if bias20:
        bias20_dislocation = abs(bias20 - 1.0) * 200
        bias20_score = max(0, min(100, bias20_dislocation))
        score += bias20_score * 0.50
    elif bias: # Fallback
        score += bias_score * 0.50

    # 3. Penalties
    # HV Rank Trap: High VRP Structural but extremely low realized vol
    hv_rank = metrics.get('hv_rank')
    trap_threshold = rules.get('hv_rank_trap_threshold', 15.0)
    rich_threshold = rules.get('vrp_structural_rich_threshold', 1.0)
    
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
    held_symbols: Optional[List[str]] = None,
    min_vrp_override: Optional[float] = None
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
        min_vrp_override: Dynamically override the structural threshold from config.

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

    # Threshold Logic
    structural_threshold = min_vrp_override if min_vrp_override is not None else RULES['vrp_structural_threshold']

    for sym, metrics in data.items():
        if 'error' in metrics:
            continue

        if exclude_symbols_set and sym.upper() in exclude_symbols_set:
            excluded_symbols_skipped += 1
            continue

        iv30 = metrics.get('iv')
        hv252 = metrics.get('hv252')
        hv20 = metrics.get('hv20')
        vrp_structural = metrics.get('vrp_structural')
        price = metrics.get('price')
        earnings_date = metrics.get('earnings_date')
        sector = metrics.get('sector', 'Unknown')

        # 3.1. Compression Logic (Fallback)
        is_data_lean = False
        compression_ratio = 1.0 # Default to Neutral
        if hv20 and hv252 and hv252 > 0:
            compression_ratio = hv20 / hv252
        elif hv252:
            is_data_lean = True

        # 3.2. VRP Tactical Calculation (Stability Clamps)
        nvrp = None
        if hv20 and iv30:
            # Use configurable HV Floor to prevent division by near-zero values
            hv_floor_config = RULES.get('hv_floor_percent', 5.0)
            hv_floor = max(hv20, hv_floor_config)
            raw_nvrp = (iv30 - hv_floor) / hv_floor
            # Hard-cap NVRP at 3.0 (300%) for ranking
            nvrp = max(-0.99, min(3.0, raw_nvrp))

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
        
        if vrp_structural is None:
            missing_bias += 1
            if not show_all:
                continue
        elif vrp_structural <= structural_threshold and not show_all:
            low_bias_skipped += 1
            continue

        # HV Rank Trap Detection: Filter short vol traps (high VRP Structural in dead volatility regimes)
        hv_rank = metrics.get('hv_rank')
        rich_threshold = RULES.get('vrp_structural_rich_threshold', 1.0)
        trap_threshold = RULES.get('hv_rank_trap_threshold', 15.0)

        is_hv_rank_trap = (
            vrp_structural is not None and
            vrp_structural > rich_threshold and
            hv_rank is not None and
            hv_rank < trap_threshold
        )

        if is_hv_rank_trap and not show_all:
            hv_rank_trap_skipped += 1
            continue

        if is_illiquid and not show_illiquid:
            illiquid_skipped += 1
            continue

        # BATS Efficiency Check (Retail Focus)
        is_bats_efficient = bool(
            price
            and vrp_structural is not None
            and RULES['bats_efficiency_min_price'] <= price <= RULES['bats_efficiency_max_price']
            and vrp_structural > RULES['bats_efficiency_vrp_structural']
        )
        if is_bats_efficient:
            bats_zone_count += 1

        # Refactored flag creation
        flags = _create_candidate_flags(vrp_structural, days_to_earnings, compression_ratio, nvrp, RULES)
        
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
            'VRP Structural': vrp_structural,
            'VRP Tactical': metrics.get('vrp_tactical'), # Add VRP Tactical here
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
            'is_held': bool(sym.upper() in held_symbols_set),
            'is_data_lean': is_data_lean
        }

        # Data quality warning for extreme negative NVRP (FINDING-006)
        if nvrp is not None and nvrp < -0.30:
            candidate_data['data_quality_warning'] = True
            candidate_data['nvrp_warning'] = "Unusual: IV significantly below HV"

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
    
    bias_note = "All symbols (no bias filter)" if show_all else f"VRP Structural (IV / HV) > {structural_threshold}"
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
        exclude_asset_classes=exclude_asset_classes,
        min_vrp_override=min_vol_bias if min_vol_bias > 0 else None
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
