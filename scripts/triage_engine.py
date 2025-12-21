"""
Triage Engine Module

Handles position triage logic, action detection, and position classification.
Extracted from analyze_portfolio.py to improve maintainability.
"""

from datetime import datetime
from typing import Dict, List, Optional, Any, TypedDict

# Import common utilities
try:
    from .portfolio_parser import parse_currency, parse_dte, get_root_symbol, is_stock_type
    from .strategy_detector import identify_strategy, map_strategy_to_id
except ImportError:
    from portfolio_parser import parse_currency, parse_dte, get_root_symbol, is_stock_type
    from strategy_detector import identify_strategy, map_strategy_to_id


class TriageResult(TypedDict, total=False):
    """Type definition for a triage result."""
    root: str
    strategy_name: str
    price: float
    is_stale: bool
    vrp_structural: Optional[float]
    proxy_note: Optional[str]
    net_pl: float
    pl_pct: Optional[float]
    dte: int
    action_code: Optional[str]
    logic: str
    sector: str
    delta: float
    gamma: float # NEW
    is_hedge: bool  # NEW: True if position is a structural hedge
    data_quality_warning: bool # NEW: True if NVRP is suspicious
    futures_multiplier_warning: Optional[str]


class TriageContext(TypedDict, total=False):
    """Type definition for triage context data."""
    market_data: Dict[str, Any]
    rules: Dict[str, Any]
    market_config: Dict[str, Any]
    strategies: Dict[str, Any]
    traffic_jam_friction: float
    portfolio_beta_delta: float  # NEW: Total portfolio delta for hedge validation
    net_liquidity: float # NEW: For size threat checks


class TriageMetrics(TypedDict, total=False):
    """Type definition for portfolio-level triage metrics."""
    total_net_pl: float
    total_beta_delta: float
    total_portfolio_theta: float
    total_portfolio_theta_vrp_adj: float  # VRP-adjusted theta (quality-weighted)
    total_portfolio_vega: float
    total_portfolio_gamma: float # NEW
    total_liquidity_cost: float
    total_abs_theta: float
    total_option_legs: int
    friction_horizon_days: float
    total_capital_at_risk: float


def detect_hedge_tag(
    root: str,
    strategy_name: str,
    strategy_delta: float,
    portfolio_beta_delta: float,
    rules: Dict[str, Any]
) -> bool:
    """
    Determine if a position qualifies as a structural portfolio hedge.

    A position is a hedge if:
    1. Underlying is a broad market index (SPY, QQQ, IWM, etc.)
    2. Strategy is protective (Long Put, Put Vertical, Put Diagonal)
    3. Position delta is negative (below threshold)
    4. (Optional) Portfolio is net long

    Args:
        root: Root symbol of the position (e.g., "SPY")
        strategy_name: Identified strategy name (e.g., "Long Put")
        strategy_delta: Net delta of the position cluster
        portfolio_beta_delta: Total portfolio beta-weighted delta
        rules: Trading rules configuration

    Returns:
        True if position qualifies as a hedge, False otherwise
    """
    # Get hedge rules from config with safe defaults
    hedge_rules = rules.get('hedge_rules', {})

    # Check if hedge detection is enabled
    if not hedge_rules.get('enabled', False):
        return False

    # Default values if not in config
    index_symbols = hedge_rules.get('index_symbols', ['SPY', 'QQQ', 'IWM'])
    qualifying_strategies = hedge_rules.get('qualifying_strategies', ['Long Put', 'Vertical Spread (Put)'])
    delta_threshold = hedge_rules.get('delta_threshold', -5)
    require_portfolio_long = hedge_rules.get('require_portfolio_long', True)

    # Check 1: Is underlying a broad market index?
    if root not in index_symbols:
        return False

    # Check 2: Is strategy protective?
    if strategy_name not in qualifying_strategies:
        return False

    # Check 3: Is position delta negative enough?
    if strategy_delta >= delta_threshold:
        return False

    # Check 4: Is portfolio actually long? (only if required)
    if require_portfolio_long and portfolio_beta_delta <= 0:
        return False

    # All conditions met - this is a hedge
    return True


def validate_futures_delta(
    root: str,
    beta_delta: float,
    market_config: Dict[str, Any],
    rules: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Validate that futures positions have plausible beta-weighted delta values.

    Detects potential multiplier issues by checking if futures delta is
    suspiciously small (suggesting raw broker delta was not multiplied).

    ASSUMPTION: Broker CSV 'beta_delta' column should contain BETA-WEIGHTED values
    (i.e., already multiplied by contract multiplier and normalized to SPY-equivalent).
    If your broker provides raw delta, pre-process the CSV before importing.

    Args:
        root: Root symbol (e.g., '/ES', 'AAPL')
        beta_delta: Beta-weighted delta value from broker CSV
        market_config: Market configuration containing FUTURES_MULTIPLIERS
        rules: Trading rules containing validation thresholds

    Returns:
        Dict with keys:
            - is_futures: bool (True if symbol is a futures contract)
            - multiplier: float (contract multiplier from config, or 1.0)
            - potential_issue: bool (True if delta looks suspiciously small)
            - expected_min: float (minimum expected abs(delta) for this contract)
            - message: str (human-readable warning if issue detected)
    """
    result = {
        'is_futures': False,
        'multiplier': 1.0,
        'potential_issue': False,
        'expected_min': 0.0,
        'message': ''
    }

    # Only check symbols starting with '/'
    if not root.startswith('/'):
        return result

    result['is_futures'] = True

    # Get multiplier from config
    futures_multipliers = market_config.get('FUTURES_MULTIPLIERS', {})
    multiplier = futures_multipliers.get(root, 1.0)
    result['multiplier'] = multiplier

    # Get validation thresholds from rules
    validation_rules = rules.get('futures_delta_validation', {})
    if not validation_rules.get('enabled', True):
        return result

    min_delta_threshold = validation_rules.get('min_abs_delta_threshold', 1.0)
    result['expected_min'] = min_delta_threshold

    # Check if delta is suspiciously small for a futures position
    if abs(beta_delta) < min_delta_threshold and abs(beta_delta) > 0:
        result['potential_issue'] = True
        result['message'] = (
            f"Futures delta ({beta_delta:.2f}) appears unmultiplied. "
            f"Expected: delta x {multiplier} = {beta_delta * multiplier:.1f} SPY-eq. "
            f"Verify broker CSV contains beta-weighted values."
        )

    return result


def calculate_days_held(legs: List[Dict[str, Any]]) -> int:
    """
    Calculate the number of days the position has been held.
    Supports standard date formats or "Xd" strings (e.g. "12d").
    Returns the maximum days held (earliest entry) found in the legs.
    """
    max_days = 0
    earliest_date = None
    
    for leg in legs:
        open_date_str = leg.get('Open Date')
        if not open_date_str:
            continue
            
        # Case 1: "12d" format
        if open_date_str.lower().endswith('d'):
            try:
                days = int(open_date_str.lower().replace('d', '').strip())
                if days > max_days:
                    max_days = days
                continue
            except ValueError:
                pass

        # Case 2: Date string
        try:
            # Try flexible parsing
            for fmt in ('%Y-%m-%d', '%m/%d/%Y', '%Y/%m/%d'):
                try:
                    dt = datetime.strptime(open_date_str, fmt).date()
                    if earliest_date is None or dt < earliest_date:
                        earliest_date = dt
                    break
                except ValueError:
                    continue
        except Exception:
            pass
    
    if earliest_date:
        calc_days = (datetime.now().date() - earliest_date).days
        if calc_days > max_days:
            max_days = calc_days
            
    return max_days


def triage_cluster(
    legs: List[Dict[str, Any]],
    context: TriageContext
) -> TriageResult:
    """
    Triage a single strategy cluster and determine action code.

    Args:
        legs: List of position legs forming a strategy
        context: Triage context with market data, rules, and configs

    Returns:
        TriageResult with action code and logic
    """
    market_data = context['market_data']
    rules = context['rules']
    market_config = context['market_config']
    strategies = context['strategies']
    traffic_jam_friction = context['traffic_jam_friction']
    net_liquidity = context.get('net_liquidity', 50000.0) # Default if missing

    root = get_root_symbol(legs[0]['Symbol'])

    # Calculate DTE only for option legs
    option_legs = [l for l in legs if not is_stock_type(l['Type'])]
    dtes = [parse_dte(l['DTE']) for l in option_legs]
    dte = min(dtes) if dtes else 0

    strategy_name = identify_strategy(legs)
    net_pl = sum(parse_currency(l['P/L Open']) for l in legs)

    # Calculate net cost BEFORE using it in map_strategy_to_id
    net_cost = sum(parse_currency(l['Cost']) for l in legs)

    # Resolve Strategy Config
    strategy_id = map_strategy_to_id(strategy_name, net_cost)
    strategy_config = strategies.get(strategy_id)

    # Set Defaults from Rules
    target_profit_pct = rules['profit_harvest_pct']
    gamma_trigger_dte = rules['gamma_dte_threshold']
    earnings_stance = "avoid" # Default to caution

    # Override with Strategy Specifics if available
    if strategy_config:
        target_profit_pct = strategy_config['management']['profit_target_pct']
        gamma_trigger_dte = strategy_config['metadata']['gamma_trigger_dte']
        earnings_stance = strategy_config['metadata'].get('earnings_stance', 'avoid')

    # --- Greek Aggregation ---
    # ASSUMPTION: Broker CSV 'beta_delta' column contains BETA-WEIGHTED delta values.
    # For futures, this means: raw_delta * contract_multiplier * (underlying_beta / SPY).
    # If your broker provides raw delta, pre-multiply before importing.
    # See: docs/TECHNICAL_ARCHITECTURE.md Section 3.5 for details.

    strategy_delta = 0.0
    strategy_gamma = 0.0
    futures_delta_warnings = []

    for l in legs:
        b_delta = parse_currency(l['beta_delta'])
        strategy_delta += b_delta

        # Validate futures delta looks reasonable (not raw/unmultiplied)
        leg_root = get_root_symbol(l['Symbol'])
        futures_check = validate_futures_delta(
            root=leg_root,
            beta_delta=b_delta,
            market_config=market_config,
            rules=rules
        )
        if futures_check['potential_issue']:
            futures_delta_warnings.append(futures_check['message'])

        # Aggregate Gamma (Beta-weighted Gamma if available, else raw)
        b_gamma = parse_currency(l.get('Gamma', '0'))
        strategy_gamma += b_gamma

    pl_pct = None
    # Treat negatives as credits received, positives as debits paid
    if net_cost < 0:
        max_profit = abs(net_cost)
        if max_profit > 0:
            pl_pct = net_pl / max_profit
    elif net_cost > 0:
        pl_pct = net_pl / net_cost

    # Calculate Days Held for Velocity
    days_held = calculate_days_held(legs)

    # Initialize variables
    action_code = None
    logic = ""
    is_winner = False

    # Retrieve live data
    m_data = market_data.get(root, {})
    vrp_structural = m_data.get('vrp_structural', 0)
    if vrp_structural is None: vrp_structural = 0
    vrp_tactical = m_data.get('vrp_tactical', 1.0) # For expansion checks

    live_price = m_data.get('price', 0)
    is_stale = m_data.get('is_stale', False)
    earnings_date = m_data.get('earnings_date')
    sector = m_data.get('sector', 'Unknown')
    proxy_note = m_data.get('proxy')

    # --- 0. Probabilistic Size Threat Check (VaR Contribution) ---
    # Check if a 2SD move (-95% confidence) causes a loss > 5% of Net Liq
    is_size_threat = False
    size_logic = ""
    
    # Need Beta IV for Expected Move calculation
    beta_rules = rules.get('beta_rules', {})
    beta_sym = rules.get('beta_weighted_symbol', 'SPY')
    beta_data = market_data.get(beta_sym, {})
    beta_iv = beta_data.get('iv', 15.0)
    beta_price = beta_data.get('price', 0.0)
    
    if beta_price > 0:
        em_1sd = beta_price * (beta_iv / 100.0 / 15.87) # 15.87 approx sqrt(252)
        move_2sd = em_1sd * -2.0 # Downward 2-sigma move
        
        # Calculate cluster specific 2SD loss
        # Loss = (Delta * Move) + (0.5 * Gamma * Move^2)
        # We use strategy_delta and strategy_gamma calculated earlier
        loss_at_2sd = (strategy_delta * move_2sd) + (0.5 * strategy_gamma * (move_2sd ** 2))
        
        # Flag if loss > 5% of Net Liq
        size_threshold = net_liquidity * rules.get('size_threat_pct', 0.05)
        if abs(loss_at_2sd) > size_threshold and loss_at_2sd < 0:
            is_size_threat = True
            usage_pct = abs(loss_at_2sd) / net_liquidity
            size_logic = f"Tail Risk: {usage_pct:.1%} of Net Liq in -2SD move"


    # --- 0. Expiration Day Check (Highest Priority) ---
    if dte == 0:
        action_code = "EXPIRING"
        logic = "Expiration Day - Manual Management Required"

    # --- 1. Harvest Logic (Enhanced with Velocity) ---
    # Standard Harvest
    if net_cost < 0 and pl_pct is not None and pl_pct >= target_profit_pct:
        action_code = "HARVEST"
        logic = f"Profit {pl_pct:.1%} (Target: {target_profit_pct:.0%})"
        is_winner = True
    
    # Velocity Harvest (Early Profit)
    # If profit > 25% AND held < 5 days
    elif net_cost < 0 and pl_pct is not None and pl_pct >= 0.25 and 0 < days_held < 5:
        action_code = "HARVEST"
        logic = f"Velocity: {pl_pct:.1%} in {days_held}d (Early Win)"
        is_winner = True

    # Size Threat Action (If not already harvesting)
    if not is_winner and is_size_threat:
        action_code = "SIZE_THREAT"
        logic = size_logic if size_logic else "Excessive Position Size"


    # --- 2. Defense ---
    underlying_price = parse_currency(legs[0]['Underlying Last Price'])
    price_used = "static"
    # Use live price if available
    if live_price:
        underlying_price = live_price
        price_used = "live_stale" if is_stale else "live"

    is_tested = False
    for l in legs:
        # Only check option legs for "tested" status
        if is_stock_type(l['Type']): continue
        qty = parse_currency(l['Quantity'])
        otype = l['Call/Put']
        strike = parse_currency(l['Strike Price'])
        if qty < 0:
            if otype == 'Call' and underlying_price > strike: is_tested = True
            elif otype == 'Put' and underlying_price < strike: is_tested = True

    if not is_winner and not action_code and is_tested and dte < gamma_trigger_dte:
        action_code = "DEFENSE"
        logic = f"Tested & < {gamma_trigger_dte} DTE"

    # --- 3. Gamma Zone ---
    if not is_winner and not action_code and not is_tested and dte < gamma_trigger_dte and dte > 0:
        action_code = "GAMMA"
        logic = f"< {gamma_trigger_dte} DTE Risk"

    # --- 4. Hedge Detection ---
    is_hedge = detect_hedge_tag(
        root=root,
        strategy_name=strategy_name,
        strategy_delta=strategy_delta,
        portfolio_beta_delta=context.get('portfolio_beta_delta', 0.0),
        rules=rules
    )

    # 4.5. Hedge Check
    if is_hedge and not is_winner and not action_code and not is_tested and dte > gamma_trigger_dte:
        if pl_pct is not None and rules['dead_money_pl_pct_low'] <= pl_pct <= rules['dead_money_pl_pct_high']:
            if vrp_structural is not None and vrp_structural < rules['dead_money_vrp_structural_threshold']:
                action_code = "HEDGE_CHECK"
                logic = f"Protective hedge on {root}. Review utility."

    # --- 5. Toxic Theta (ZOMBIE) ---
    # Triggered if Exp. Alpha < Raw Theta (The market is underpricing the risk of movement)
    # Only flag if not already a winner/defense/gamma and P/L is relatively stagnant
    if not is_winner and not action_code and not is_tested and dte > gamma_trigger_dte and not is_hedge:
        # Calculate Alpha for this cluster specifically
        cluster_alpha = 0.0
        if vrp_structural > 0:
            cluster_alpha = strategy_delta * vrp_structural # Simplified proxy for the check
            # Real check: is VRP below the 'dead money' threshold?
            if vrp_structural < rules.get('dead_money_vrp_structural_threshold', 0.80):
                if pl_pct is not None and rules['dead_money_pl_pct_low'] <= pl_pct <= rules['dead_money_pl_pct_high']:
                    action_code = "TOXIC"
                    logic = f"Toxic Theta: Expected Yield ({vrp_structural:.2f}x) < Statistical Cost"
            elif vrp_structural == 0 and 'IV Rank' in legs[0] and parse_currency(legs[0]['IV Rank']) < rules['low_ivr_threshold']:
                 action_code = "TOXIC"
                 logic = "Low IVR (Stale) & Flat P/L"

    # --- 6. Earnings Check (Enhanced with Stance) ---
    earnings_note = ""
    if earnings_date and earnings_date != "Unavailable":
        try:
            edate = datetime.fromisoformat(earnings_date).date()
            days_to_earn = (edate - datetime.now().date()).days
            
            if 0 <= days_to_earn <= rules['earnings_days_threshold']:
                earnings_note = f"Earnings {days_to_earn}d"
                
                # Logic based on Earnings Stance
                if earnings_stance == "avoid":
                    # Standard warning for short vol
                    if not action_code:
                        action_code = "EARNINGS_WARNING"
                        logic = "Binary Event Risk (Avoid)"
                    elif action_code == "HARVEST":
                        # If harvesting, emphasize closing before event
                        logic = f"{logic} | Close before Earnings!"
                
                elif earnings_stance == "long_vol":
                    # Opportunity for long vol
                    earnings_note = f"{earnings_note} (Play)"
                    # Do NOT flag as warning, just append note
                
                elif earnings_stance == "neutral":
                    # Just informational
                    pass
                
                # Append note to logic if not already main reason
                if action_code != "EARNINGS_WARNING":
                     logic = f"{logic} | {earnings_note}" if logic else earnings_note

        except (ValueError, TypeError):
            pass

    # --- 7. VRP Momentum (SCALABLE) ---
    # Triggered if Tactical VRP is surging above Structural (Fresh Opportunity)
    # AND we aren't already oversized or in trouble.
    if not action_code and not is_tested and dte > gamma_trigger_dte and not is_hedge:
        if vrp_tactical > (vrp_structural + 0.4) and vrp_tactical > 1.5:
            # Safety check: Only suggest scaling if current Tail Risk is low (< 2% of Net Liq)
            # This prevents over-sizing already significant positions.
            if abs(loss_at_2sd) < (0.02 * net_liquidity) and (pl_pct or 0) < 0.25:
                action_code = "SCALABLE"
                logic = f"VRP Surge: Tactical markup ({vrp_tactical:.2f}) is significantly above trend. High Alpha Opportunity."

    price_value = live_price if live_price else parse_currency(legs[0]['Underlying Last Price'])
    if (price_used != "live" or is_stale) and not is_winner and dte < gamma_trigger_dte:
        note = "Price stale/absent; tested status uncertain"
        logic = f"{logic} | {note}" if logic else note

    # --- Data Quality Warning ---
    # nvrp check
    quality_warning = False
    warning_threshold = rules.get('nvrp_quality_warning_threshold', 0.50)
    
    # Calculate NVRP for check
    hv20 = m_data.get('hv20')
    iv30 = m_data.get('iv')
    if hv20 and hv20 > 0 and iv30:
        nvrp = (iv30 - hv20) / hv20
        if abs(nvrp) > warning_threshold:
            quality_warning = True

    return {
        'root': root,
        'strategy_name': strategy_name,
        'price': price_value,
        'is_stale': bool(is_stale),
        'vrp_structural': vrp_structural if vrp_structural is not None else None,
        'proxy_note': proxy_note,
        'net_pl': net_pl,
        'pl_pct': pl_pct,
        'dte': dte,
        'action_code': action_code,
        'logic': logic,
        'sector': sector,
        'delta': strategy_delta,
        'gamma': strategy_gamma,
        'is_hedge': is_hedge,
        'data_quality_warning': quality_warning,
        'futures_multiplier_warning': futures_delta_warnings[0] if futures_delta_warnings else None
    }


def triage_portfolio(
    clusters: List[List[Dict[str, Any]]],
    context: TriageContext
) -> tuple[List[TriageResult], TriageMetrics]:
    """
    Triage all clusters in a portfolio and calculate portfolio-level metrics.

    Args:
        clusters: List of strategy clusters
        context: Triage context with market data, rules, and configs

    Returns:
        Tuple of (position_reports, metrics)
    """
    market_config = context['market_config']
    rules = context['rules']
    traffic_jam_friction = context['traffic_jam_friction']

    all_position_reports = []
    total_net_pl = 0.0
    total_beta_delta = 0.0
    total_portfolio_theta = 0.0
    total_portfolio_theta_vrp_adj = 0.0  # VRP-adjusted theta accumulator
    total_portfolio_vega = 0.0
    total_portfolio_gamma = 0.0
    total_liquidity_cost = 0.0
    total_abs_theta = 0.0
    total_option_legs = 0
    total_capital_at_risk = 0.0

    for legs in clusters:
        if not legs:
            continue

        # Calculate per-leg metrics
        option_legs = [l for l in legs if not is_stock_type(l['Type'])]
        total_option_legs += len(option_legs)

        # Get triage result for this cluster
        triage_result = triage_cluster(legs, context)
        all_position_reports.append(triage_result)

        # Accumulate portfolio metrics
        total_net_pl += triage_result['net_pl']
        total_beta_delta += triage_result['delta']

        # Calculate capital at risk (sum of absolute cost basis for all positions)
        net_cost = sum(parse_currency(l['Cost']) for l in legs)
        total_capital_at_risk += abs(net_cost)

        # Calculate theta, vega and friction metrics
        cluster_theta_raw = 0.0  # Track raw theta for this cluster
        for l in legs:
            leg_theta = parse_currency(l['Theta'])
            total_portfolio_theta += leg_theta
            cluster_theta_raw += leg_theta
            total_abs_theta += abs(leg_theta)

            # Vega/Gamma Aggregation
            leg_vega = parse_currency(l.get('Vega', '0'))
            total_portfolio_vega += leg_vega
            
            leg_gamma = parse_currency(l.get('Gamma', '0'))
            total_portfolio_gamma += leg_gamma

            # Friction Horizon: Calculate liquidity cost (Ask - Bid) * Qty * Multiplier
            bid = parse_currency(l['Bid'])
            ask = parse_currency(l['Ask'])
            qty = abs(parse_currency(l['Quantity']))

            if ask > bid and qty > 0:
                spread = ask - bid

                # Get multiplier from config or default to 100 for standard options
                multiplier = 100.0
                sym = l['Symbol'].upper()

                # Check if this is a future and get its multiplier from config
                futures_multipliers = market_config.get('FUTURES_MULTIPLIERS', {})
                if sym.startswith('/'):
                    # Try exact match first
                    if sym in futures_multipliers:
                        multiplier = futures_multipliers[sym]
                    else:
                        # Try prefix match (e.g., /ESZ24 matches /ES)
                        for future_prefix, future_mult in futures_multipliers.items():
                            if sym.startswith(future_prefix):
                                multiplier = future_mult
                                break

                liquidity_cost = spread * qty * multiplier
                total_liquidity_cost += liquidity_cost

        # Apply VRP adjustment to cluster theta
        # Get VRP Tactical from market_data for this cluster's root symbol
        root = get_root_symbol(legs[0]['Symbol'])
        m_data = context['market_data'].get(root, {})
        
        # VRP Tactical is the ratio (IV / HV20)
        vrp_t = m_data.get('vrp_tactical')

        if vrp_t is not None:
            # CLAMPING Logic for Portfolio Aggregation
            # Prevent single-symbol data errors (like 1% IV) from skewing total portfolio quality
            nvrp_floor = context['rules'].get('nvrp_aggregation_floor', -0.50)
            nvrp_ceil = context['rules'].get('nvrp_aggregation_ceiling', 1.00)
            
            # Convert VRP Tactical (Ratio) to NVRP (Markup) for clamping
            # VRP 1.5 -> NVRP 0.5. VRP 0.1 -> NVRP -0.9.
            nvrp_val = vrp_t - 1.0
            clamped_nvrp = max(nvrp_floor, min(nvrp_ceil, nvrp_val))
            
            # Re-convert to Clamped Ratio for multiplication
            clamped_ratio = 1.0 + clamped_nvrp
            
            # Alpha Theta = Raw Theta * Clamped Tactical Ratio
            cluster_theta_vrp_adj = cluster_theta_raw * clamped_ratio
        else:
            # Fallback: If VRP Tactical unavailable, use VRP Structural
            vrp_s = m_data.get('vrp_structural', 1.0)
            cluster_theta_vrp_adj = cluster_theta_raw * vrp_s

        total_portfolio_theta_vrp_adj += cluster_theta_vrp_adj

    # Calculate Friction Horizon (Φ)
    friction_horizon_days = 0.0
    if total_abs_theta > rules.get('friction_horizon_min_theta', 0.01):
        friction_horizon_days = total_liquidity_cost / total_abs_theta
    elif total_liquidity_cost > 0:
        friction_horizon_days = traffic_jam_friction  # Infinite friction (trapped)

    metrics: TriageMetrics = {
        'total_net_pl': total_net_pl,
        'total_beta_delta': total_beta_delta,
        'total_portfolio_theta': total_portfolio_theta,
        'total_portfolio_theta_vrp_adj': total_portfolio_theta_vrp_adj,
        'total_portfolio_vega': total_portfolio_vega,
        'total_portfolio_gamma': total_portfolio_gamma,
        'total_liquidity_cost': total_liquidity_cost,
        'total_abs_theta': total_abs_theta,
        'total_option_legs': total_option_legs,
        'friction_horizon_days': friction_horizon_days,
        'total_capital_at_risk': total_capital_at_risk
    }

    return all_position_reports, metrics


def get_position_aware_opportunities(
    positions: List[Dict[str, Any]],
    clusters: List[List[Dict[str, Any]]],
    net_liquidity: float,
    rules: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Identifies concentrated vs. held positions and queries the vol screener.

    The "Stacking Rule":
    - Concentrated: >5% of Net Liq OR >= 3 distinct strategy clusters on same root
    - Held: All other positions in portfolio

    Args:
        positions: List of normalized position dictionaries
        clusters: List of strategy clusters from cluster_strategies()
        net_liquidity: Account net liquidity value
        rules: Trading rules configuration

    Returns:
        Dict with 'meta' (excluded info) and 'candidates' (screening results)
    """
    from collections import defaultdict
    from vol_screener import get_screener_results

    # 1. Extract all unique roots
    held_roots = set()
    for pos in positions:
        root = get_root_symbol(pos.get('Symbol', ''))
        if root:
            held_roots.add(root)

    # 2. Calculate concentration per root using "Stacking Rule"
    # Group clusters by root symbol
    root_clusters = defaultdict(list)
    for cluster in clusters:
        if cluster:
            root = get_root_symbol(cluster[0].get('Symbol', ''))
            if root:
                root_clusters[root].append(cluster)

    # Calculate total cost/margin per root
    root_exposure = defaultdict(float)
    for pos in positions:
        root = get_root_symbol(pos.get('Symbol', ''))
        if root:
            # Try to get Cost (margin requirement), fallback to 0
            cost_str = pos.get('Cost', '0')
            try:
                cost = abs(float(cost_str)) if cost_str else 0.0
            except (ValueError, TypeError):
                cost = 0.0
            root_exposure[root] += cost

    # 3. Apply Stacking Rule to identify concentrated positions
    concentrated_roots_set = set()
    concentration_limit = net_liquidity * rules.get('concentration_limit_pct', 0.05)
    max_strategies = rules.get('max_strategies_per_symbol', 3)

    # Track processed groups to avoid duplicates
    processed_groups = set()

    # Expand exposures to include equivalent symbols (futures ↔ ETF proxies)
    if not rules.get('allow_proxy_stacking', False):
        # Import the function from common.py
        try:
            from .common import get_equivalent_exposures
        except ImportError:
            from common import get_equivalent_exposures
    else:
        # If stacking is allowed, each symbol is its own group
        get_equivalent_exposures = lambda x: {x}

    for root in held_roots:
        # Get exposure group for this root
        group_members = get_equivalent_exposures(root)

        # Only consider equivalents we actually hold
        held_group_members = group_members & held_roots

        # Create group ID to track if we've processed this group
        group_id = tuple(sorted(held_group_members))

        if group_id in processed_groups:
            continue
        processed_groups.add(group_id)

        # Sum exposure and strategy counts across all equivalents in the group
        exposure = sum(root_exposure.get(member, 0.0) for member in held_group_members)
        strategy_count = sum(len(root_clusters.get(member, [])) for member in held_group_members)

        is_concentrated = (
            exposure > concentration_limit or
            strategy_count >= max_strategies
        )

        if is_concentrated:
            # Add ALL members of the exposure group to concentrated_roots
            concentrated_roots_set.update(held_group_members)

    concentrated_roots = list(concentrated_roots_set)

    # 4. Call vol screener with position context
    screener_results = get_screener_results(
        exclude_symbols=concentrated_roots,
        held_symbols=list(held_roots),
        min_vol_bias=rules.get('vrp_structural_threshold', 0.85),
        limit=None,
        filter_illiquid=True
    )

    # 5. Package results
    return {
        "meta": {
            "excluded_count": len(concentrated_roots),
            "excluded_symbols": concentrated_roots,
            "scan_timestamp": datetime.now().isoformat()
        },
        "candidates": screener_results.get('candidates', []),
        "summary": screener_results.get('summary', {})
    }
