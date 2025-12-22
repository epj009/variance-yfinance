import argparse
import csv
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any, Union

from get_market_data import get_market_data

# Import common utilities
try:
    from .common import map_sector_to_asset_class, warn_if_not_venv
    from .config_loader import load_trading_rules, load_system_config, load_screener_profiles
except ImportError:
    # Fallback for direct script execution
    from common import map_sector_to_asset_class, warn_if_not_venv
    from config_loader import load_trading_rules, load_system_config, load_screener_profiles

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


@dataclass
class ScreenerConfig:
    limit: Optional[int] = None
    min_vrp_structural: Optional[float] = None
    min_variance_score: Optional[float] = None
    allow_illiquid: bool = False
    exclude_sectors: List[str] = field(default_factory=list)
    include_asset_classes: List[str] = field(default_factory=list)
    exclude_asset_classes: List[str] = field(default_factory=list)
    exclude_symbols: List[str] = field(default_factory=list)
    held_symbols: List[str] = field(default_factory=list)


def load_profile_config(profile_name: str) -> ScreenerConfig:
    profiles = load_screener_profiles()
    profile_key = profile_name.lower()
    profile_data = profiles.get(profile_key)
    if profile_data is None:
        available = ", ".join(sorted(profiles.keys()))
        raise ValueError(f"Unknown profile '{profile_name}'. Available profiles: {available}")

    return ScreenerConfig(
        limit=None,
        min_vrp_structural=profile_data.get("min_vrp_structural"),
        min_variance_score=profile_data.get("min_variance_score", RULES.get("min_variance_score", 10.0)),
        allow_illiquid=profile_data.get("allow_illiquid", False),
        exclude_sectors=list(profile_data.get("exclude_sectors", []) or []),
        include_asset_classes=list(profile_data.get("include_asset_classes", []) or []),
        exclude_asset_classes=list(profile_data.get("exclude_asset_classes", []) or []),
        exclude_symbols=list(profile_data.get("exclude_symbols", []) or []),
        held_symbols=list(profile_data.get("held_symbols", []) or []),
    )

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

    mode = rules.get('liquidity_mode', 'volume')

    # 1. Check Activity (Volume or OI)
    if mode == 'open_interest':
        atm_oi = metrics.get('atm_open_interest', 0)
        # Fallback to volume if OI is missing (e.g. data error)
        if atm_oi is None:
             atm_volume = metrics.get('atm_volume', 0)
             if atm_volume is not None and atm_volume < rules['min_atm_volume']:
                 return True
        elif atm_oi < rules.get('min_atm_open_interest', 500):
            return True
    else:
        # Default: Volume Mode
        atm_volume = metrics.get('atm_volume', 0)
        if atm_volume is not None and atm_volume < rules['min_atm_volume']:
            return True

    # 2. Per-Leg Liquidity Check (FINDING-002)
    # Ensure NEITHER the call nor the put is "dead" (zero volume or excessive spread)
    legs = [
        ('call', metrics.get('call_bid'), metrics.get('call_ask'), metrics.get('call_vol')),
        ('put', metrics.get('put_bid'), metrics.get('put_ask'), metrics.get('put_vol'))
    ]
    
    for side, bid, ask, vol in legs:
        # Note: In OI mode, we don't necessarily fail on 0 volume per leg
        # BUT we still fail on broken spreads (slippage)
            
        # Check per-leg slippage
        if bid is not None and ask is not None:
            mid = (bid + ask) / 2
            if mid > 0:
                slippage = (ask - bid) / mid
                if slippage > rules['max_slippage_pct']:
                    return True
            else:
                return True # Bid/Ask are 0 or negative

    return False

def _create_candidate_flags(vrp_structural: Optional[float], days_to_earnings: Union[int, str], compression_ratio: Optional[float], vrp_t_markup: Optional[float], hv20: Optional[float], hv60: Optional[float], rules: Dict[str, Any]) -> Dict[str, bool]:
    """Creates a dictionary of boolean flags for a candidate."""
    
    # Coiled Logic: Requires BOTH long-term compression (vs 252) and medium-term compression (vs 60)
    # to avoid flagging "new normal" low vol regimes as coiled.
    is_coiled_long = (compression_ratio is not None and compression_ratio < rules.get('compression_coiled_threshold', 0.75))
    is_coiled_medium = True # Default to true if missing data
    if hv60 and hv60 > 0 and hv20:
        is_coiled_medium = (hv20 / hv60) < 0.85
        
    return {
        'is_rich': bool(vrp_structural is not None and vrp_structural > rules.get('vrp_structural_rich_threshold', 1.0)),
        'is_fair': bool(vrp_structural is not None and rules['vrp_structural_threshold'] < vrp_structural <= rules.get('vrp_structural_rich_threshold', 1.0)),
        'is_earnings_soon': bool(isinstance(days_to_earnings, int) and 0 <= days_to_earnings <= rules['earnings_days_threshold']),
        'is_coiled': bool(is_coiled_long and is_coiled_medium),
        'is_expanding': bool(compression_ratio is not None and compression_ratio > rules.get('compression_expanding_threshold', 1.25)),
        'is_cheap': bool(vrp_t_markup is not None and vrp_t_markup < rules.get('vrp_tactical_cheap_threshold', -0.10))
    }

def _determine_signal_type(flags: Dict[str, bool], vrp_t_markup: Optional[float], rules: Dict[str, Any]) -> str:
    """
    Synthesizes multiple metrics into a single 'Signal Type' for the TUI.
    Hierarchy: EVENT > DISCOUNT > RICH > BOUND > FAIR
    """
    if flags['is_earnings_soon']:
        return "EVENT"
    
    if flags.get('is_cheap'): # VRP Tactical Markup < -10%
        return "DISCOUNT"

    # Rich Logic: High markup takes precedence over Coiled state
    # Priority 1: Tactical VRP Markup > 20%
    if vrp_t_markup is not None and vrp_t_markup > 0.20:
        return "RICH"
    
    # Priority 2: Structural VRP (Fallback if Tactical is missing/flat)
    if flags.get('is_rich'):
        return "RICH"
        
    if flags['is_coiled']: # Ratio < 0.75
        return "BOUND"
        
    return "FAIR"

def _determine_regime_type(flags: Dict[str, bool]) -> str:
    """
    Determines the Volatility Regime based on compression flags.
    """
    if flags['is_coiled']:
        return "COILED"
    if flags['is_expanding']:
        return "EXPANDING"
    return "NORMAL"

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
        bias_dislocation = abs(bias - 1.0) * rules.get('variance_score_dislocation_multiplier', 200)
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

    # 4. Regime Penalties (Dev Mode)
    # Coiled Penalty: Recent movement is unsustainably low. 
    # High markup may be an artifact of a shrinking denominator.
    # Apply a 20% haircut to Coiled signals to favor Normal/Expanding regimes.
    if metrics.get('regime_type') == 'COILED' or metrics.get('is_coiled'):
        score *= 0.80
        
    return round(score, 1)

def screen_volatility(config: ScreenerConfig) -> Dict[str, Any]:
    """
    Scan the watchlist for high-volatility trading opportunities.

    Fetches market data, filters by Vol Bias threshold (unless min_vrp_structural <= 0), filters out illiquid names
    (unless allow_illiquid=True),
    and optionally excludes specific sectors or filters by asset class. Returns a structured report.

    Args:
        config: ScreenerConfig with filters, limits, and overrides.

    Returns:
        A dictionary containing 'candidates' (list of dicts) and 'summary' (dict).
    """
    limit = config.limit
    exclude_sectors = config.exclude_sectors or []
    include_asset_classes = config.include_asset_classes or []
    exclude_asset_classes = config.exclude_asset_classes or []
    exclude_symbols = config.exclude_symbols or []
    held_symbols = config.held_symbols or []
    allow_illiquid = config.allow_illiquid
    min_vrp_structural = config.min_vrp_structural
    show_all = min_vrp_structural is not None and min_vrp_structural <= 0

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
    low_score_skipped = 0
    missing_bias = 0
    sector_skipped = 0
    asset_class_skipped = 0
    illiquid_skipped = 0
    excluded_symbols_skipped = 0
    hv_rank_trap_skipped = 0  # Short vol trap filter
    bats_zone_count = 0 # Initialize bats zone counter
    
    # Strict Mode Counters
    data_integrity_skipped = 0
    lean_data_skipped = 0
    anomalous_data_skipped = 0
    
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
    structural_threshold = RULES['vrp_structural_threshold'] if min_vrp_structural is None else min_vrp_structural
    
    # Absolute Vol Floor: Filter out dead assets where Ratio is high only because HV is near zero
    # Example: /ZT (HV=1.5, IV=3.5 -> Ratio 2.3). Untradable noise.
    hv_floor_absolute = RULES.get('hv_floor_percent', 5.0)

    for sym, metrics in data.items():
        if 'error' in metrics:
            continue

        if exclude_symbols_set and sym.upper() in exclude_symbols_set:
            excluded_symbols_skipped += 1
            continue

        iv30 = metrics.get('iv')
        hv252 = metrics.get('hv252')
        hv60 = metrics.get('hv60')
        hv20 = metrics.get('hv20')
        vrp_structural = metrics.get('vrp_structural')
        price = metrics.get('price')
        earnings_date = metrics.get('earnings_date')
        sector = metrics.get('sector', 'Unknown')
        
        # --- FILTER: SECTOR & ASSET CLASS ---
        if exclude_sectors and sector in exclude_sectors:
            sector_skipped += 1
            continue

        asset_class = map_sector_to_asset_class(sector)
        if include_asset_classes and asset_class not in include_asset_classes:
            asset_class_skipped += 1
            continue
        if exclude_asset_classes and asset_class in exclude_asset_classes:
            asset_class_skipped += 1
            continue

        # --- FILTER: LIQUIDITY ---
        is_illiquid = _is_illiquid(sym, metrics, RULES)
        if is_illiquid and not allow_illiquid:
            illiquid_skipped += 1
            continue

        # --- FILTER: VOLATILITY REGIME (Structural) ---
        if vrp_structural is None:
            missing_bias += 1
            if not show_all: continue
        elif vrp_structural <= structural_threshold and not show_all:
            low_bias_skipped += 1
            continue

        # --- FILTER: LOW VOL TRAP (Denominator Effect) ---
        # If HV is below the absolute floor (e.g. 5%), the ratio is noise.
        is_low_vol_trap = (hv252 is not None and hv252 < hv_floor_absolute)
        
        if is_low_vol_trap and not show_all:
            # We treat this effectively as "Low Bias" (Not enough juice)
            # Or track it separately if we want granular stats
            hv_rank_trap_skipped += 1 # Re-using trap counter for simplicity
            continue

        # --- FILTER: HV RANK TRAP (Relative) ---
        # High Ratio but Low Rank (e.g. TSLA going sideways)
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

        # 3.1. Compression Logic (Fallback)
        is_data_lean = False
        compression_ratio = 1.0 # Default to Neutral
        if hv20 and hv252 and hv252 > 0:
            compression_ratio = hv20 / hv252
        elif hv252:
            is_data_lean = True

        # --- FILTER: DATA INTEGRITY (Strict Mode) ---
        # Reject any symbol with partial data, scaling warnings, or missing HV20
        if metrics.get('warning'):
            data_integrity_skipped += 1
            continue
            
        if is_data_lean:
            lean_data_skipped += 1
            continue

        # 3.2. VRP Tactical Calculation (Stability Clamps)
        vrp_t_markup = None
        if hv20 and iv30:
            # Use configurable HV Floor to prevent division by near-zero values
            hv_floor = max(hv20, hv_floor_absolute)
            raw_markup = (iv30 - hv_floor) / hv_floor
            # Hard-cap Markup at 3.0 (300%) for ranking
            vrp_t_markup = max(-0.99, min(3.0, raw_markup))

        # Data quality warning for extreme negative markup (FINDING-006)
        if vrp_t_markup is not None and vrp_t_markup < -0.30:
            # STRICT MODE: Skip anomalies where IV is significantly below HV
            anomalous_data_skipped += 1
            continue

        days_to_earnings = get_days_to_date(earnings_date)

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
        flags = _create_candidate_flags(vrp_structural, days_to_earnings, compression_ratio, vrp_t_markup, hv20, hv60, RULES)
        
        # Determine Signal Type
        signal_type = _determine_signal_type(flags, vrp_t_markup, RULES)
        
        # Determine Regime Type
        regime_type = _determine_regime_type(flags)
        
        # Determine Recommended Environment
        env_idea = _get_recommended_environment(signal_type)
        
        # Inject regime into metrics for scoring penalty
        metrics['is_coiled'] = flags['is_coiled']
        metrics['regime_type'] = regime_type

        # Calculate Variance Score
        variance_score = _calculate_variance_score(metrics, RULES)
        
        # --- FILTER: CONVICTION FLOOR (Dev Mode) ---
        score_floor = config.min_variance_score if config.min_variance_score is not None else 10.0
        if variance_score < score_floor and not show_all:
            low_score_skipped += 1
            continue

        # Prepare candidate data for return
        candidate_data = {
            'Symbol': sym,
            'Price': price,
            'IV30': iv30,
            'HV252': hv252,
            'HV20': hv20,
            'Compression Ratio': compression_ratio,
            'VRP Structural': vrp_structural,
            'VRP Tactical': metrics.get('vrp_tactical'), # Ratio
            'VRP_Tactical_Markup': vrp_t_markup, # Renamed from NVRP
            'Score': variance_score, # The Golden Metric
            'Signal': signal_type,
            'Regime': regime_type, # New field
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

        # Data quality warning for extreme negative markup (FINDING-006)
        if vrp_t_markup is not None and vrp_t_markup < -0.30:
            candidate_data['data_quality_warning'] = True
            candidate_data['nvrp_warning'] = "Unusual: IV significantly below HV"

        candidate_data.update(flags)
        candidates_with_status.append(candidate_data)
    
    # 4. Sort by signal quality: Tactical Markup (Desc), then Variance Score (Desc), then Proxy bias last
    def _signal_key(c):
        # Sorting Logic:
        # 1. Primary Key: VRP_Tactical_Markup (Descending). Fattest premium markup over movement.
        # 2. Secondary Key: Variance Score (Descending). Structural edge.
        # 3. Tertiary Key: Data Quality (0=Real, 1=Proxy). Lower is better.
        score = c['Score']
        vtm = c.get('VRP_Tactical_Markup') if c.get('VRP_Tactical_Markup') is not None else -9.9 # Handle 0.0 correctly
        proxy = c.get('Proxy')
        quality = 1 if proxy else 0
        return (vtm, score, -quality) # Sort by VTM DESC, then Score DESC, then Quality ASC
        
    candidates_with_status.sort(key=_signal_key, reverse=True)
    
    bias_note = "All symbols (no bias filter)" if show_all else f"VRP Structural (IV / HV) > {structural_threshold}"
    
    liq_mode = RULES.get('liquidity_mode', 'volume')
    if allow_illiquid:
        liquidity_note = "Illiquid included"
    elif liq_mode == 'open_interest':
        liquidity_note = f"Illiquid filtered (ATM OI < {RULES.get('min_atm_open_interest', 500)}, slippage > {RULES['max_slippage_pct']*100:.1f}%)"
    else:
        liquidity_note = f"Illiquid filtered (ATM vol < {RULES['min_atm_volume']}, slippage > {RULES['max_slippage_pct']*100:.1f}%)"

    summary = {
        "scanned_symbols_count": len(symbols),
        "low_bias_skipped_count": low_bias_skipped,
        "low_score_skipped_count": low_score_skipped,
        "sector_skipped_count": sector_skipped,
        "asset_class_skipped_count": asset_class_skipped,
        "missing_bias_count": missing_bias,
        "illiquid_skipped_count": illiquid_skipped,
        "excluded_symbols_skipped_count": excluded_symbols_skipped,
        "hv_rank_trap_skipped_count": hv_rank_trap_skipped,
        "bats_efficiency_zone_count": bats_zone_count,
        "data_integrity_skipped_count": data_integrity_skipped,
        "lean_data_skipped_count": lean_data_skipped,
        "anomalous_data_skipped_count": anomalous_data_skipped,
        "filter_note": f"{bias_note}; {liquidity_note}"
    }

    return {"candidates": candidates_with_status, "summary": summary}

if __name__ == "__main__":
    warn_if_not_venv()

    parser = argparse.ArgumentParser(description='Screen for high volatility opportunities.')
    parser.add_argument('limit', type=int, nargs='?', help='Limit the number of symbols to scan (optional)')
    parser.add_argument('--profile', type=str, default='balanced', help='Profile name from config/screener_profiles.json')
    parser.add_argument('--exclude-sectors', type=str, help='Comma-separated list of sectors to exclude (e.g., "Financial Services,Technology")')
    parser.add_argument('--include-asset-classes', type=str, help='Comma-separated list of asset classes to include (e.g., "Commodity,FX"). Options: Equity, Commodity, Fixed Income, FX, Index')
    parser.add_argument('--exclude-asset-classes', type=str, help='Comma-separated list of asset classes to exclude (e.g., "Equity"). Options: Equity, Commodity, Fixed Income, FX, Index')
    parser.add_argument('--exclude-symbols', type=str, help='Comma-separated list of symbols to exclude (e.g., "NVDA,TSLA,AMD")')
    parser.add_argument('--held-symbols', type=str, help='Comma-separated list of symbols currently in portfolio (will be flagged as held, not excluded)')

    args = parser.parse_args()
    try:
        config = load_profile_config(args.profile)
    except ValueError as exc:
        print(json.dumps({"error": str(exc)}, indent=2), file=sys.stderr)
        sys.exit(2)

    if args.limit is not None:
        config.limit = args.limit

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

    if exclude_list:
        config.exclude_sectors = exclude_list
    if include_assets:
        config.include_asset_classes = include_assets
    if exclude_assets:
        config.exclude_asset_classes = exclude_assets
    if exclude_symbols_list:
        config.exclude_symbols = exclude_symbols_list
    if held_symbols_list:
        config.held_symbols = held_symbols_list

    report_data = screen_volatility(config)
    
    if "error" in report_data:
        print(json.dumps(report_data, indent=2))
        sys.exit(1)

    print(json.dumps(report_data, indent=2))
