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
    vol_bias: Optional[float]
    proxy_note: Optional[str]
    net_pl: float
    pl_pct: Optional[float]
    dte: int
    action_code: Optional[str]
    logic: str
    sector: str
    delta: float
    is_hedge: bool  # NEW: True if position is a structural hedge


class TriageContext(TypedDict, total=False):
    """Type definition for triage context data."""
    market_data: Dict[str, Any]
    rules: Dict[str, Any]
    market_config: Dict[str, Any]
    strategies: Dict[str, Any]
    traffic_jam_friction: float
    portfolio_beta_delta: float  # NEW: Total portfolio delta for hedge validation


class TriageMetrics(TypedDict, total=False):
    """Type definition for portfolio-level triage metrics."""
    total_net_pl: float
    total_beta_delta: float
    total_portfolio_theta: float
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

    # Override with Strategy Specifics if available
    if strategy_config:
        target_profit_pct = strategy_config['management']['profit_target_pct']
        gamma_trigger_dte = strategy_config['metadata']['gamma_trigger_dte']

    strategy_delta = 0.0
    for l in legs:
        b_delta = parse_currency(l['beta_delta'])
        strategy_delta += b_delta

    pl_pct = None
    # Treat negatives as credits received, positives as debits paid
    if net_cost < 0:
        max_profit = abs(net_cost)
        if max_profit > 0:
            pl_pct = net_pl / max_profit
    elif net_cost > 0:
        pl_pct = net_pl / net_cost

    # Initialize variables
    action_code = None
    logic = ""
    is_winner = False

    # Retrieve live data
    m_data = market_data.get(root, {})
    vol_bias = m_data.get('vol_bias', 0)
    if vol_bias is None: vol_bias = 0

    live_price = m_data.get('price', 0)
    is_stale = m_data.get('is_stale', False)
    earnings_date = m_data.get('earnings_date')
    sector = m_data.get('sector', 'Unknown')
    proxy_note = m_data.get('proxy')

    # 1. Harvest (Short Premium only)
    if net_cost < 0 and pl_pct is not None and pl_pct >= target_profit_pct:
        action_code = "HARVEST"
        logic = f"Profit {pl_pct:.1%} (Target: {target_profit_pct:.0%})"
        is_winner = True

    # 2. Defense
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

    if not is_winner and is_tested and dte < gamma_trigger_dte:
        action_code = "DEFENSE"
        logic = f"Tested & < {gamma_trigger_dte} DTE"

    # 3. Gamma Zone (apply even if P/L% is unknown)
    if not is_winner and not is_tested and dte < gamma_trigger_dte and dte > 0:
        action_code = "GAMMA"
        logic = f"< {gamma_trigger_dte} DTE Risk"

    # 4. Hedge Detection (Protect structural hedges from ZOMBIE flag)
    is_hedge = detect_hedge_tag(
        root=root,
        strategy_name=strategy_name,
        strategy_delta=strategy_delta,
        portfolio_beta_delta=context.get('portfolio_beta_delta', 0.0),
        rules=rules
    )

    # 4.5. Hedge Check (Review protective positions)
    if is_hedge and not is_winner and not is_tested and dte > gamma_trigger_dte:
        # Check if this would have been flagged as ZOMBIE
        if pl_pct is not None and rules['dead_money_pl_pct_low'] <= pl_pct <= rules['dead_money_pl_pct_high']:
            if vol_bias is not None and vol_bias < rules['dead_money_vol_bias_threshold']:
                action_code = "HEDGE_CHECK"
                logic = f"Protective hedge on {root}. Review: Is protection still relevant?"

    # 5. Dead Money (Enhanced with Real-time Vol Bias) - SKIP FOR HEDGES
    if not is_winner and not is_tested and dte > gamma_trigger_dte and not is_hedge:
        if pl_pct is not None and rules['dead_money_pl_pct_low'] <= pl_pct <= rules['dead_money_pl_pct_high']:
            if vol_bias > 0 and vol_bias < rules['dead_money_vol_bias_threshold']:
                action_code = "ZOMBIE"
                logic = f"Bias {vol_bias:.2f} & Flat P/L"
            elif vol_bias == 0 and 'IV Rank' in legs[0] and parse_currency(legs[0]['IV Rank']) < rules['low_ivr_threshold']:
                 # Fallback if no live data
                 action_code = "ZOMBIE"
                 logic = "Low IVR (Stale) & Flat P/L"

    # 6. Earnings Warning
    earnings_note = ""
    if earnings_date and earnings_date != "Unavailable":
        try:
            edate = datetime.fromisoformat(earnings_date).date()
            days_to_earn = (edate - datetime.now().date()).days
            if 0 <= days_to_earn <= rules['earnings_days_threshold']:
                earnings_note = f"Earnings {days_to_earn}d (Binary Event)"
                if not action_code:
                    action_code = "EARNINGS_WARNING"
                    logic = "Binary Event Risk"
                logic = f"{logic} | {earnings_note}" if logic else earnings_note
        except (ValueError, TypeError):
            pass

    price_value = live_price if live_price else parse_currency(legs[0]['Underlying Last Price'])
    if (price_used != "live" or is_stale) and not is_winner and dte < gamma_trigger_dte:
        # If we can't rely fully on tested logic due to stale/absent live price, note it
        note = "Price stale/absent; tested status uncertain"
        logic = f"{logic} | {note}" if logic else note

    return {
        'root': root,
        'strategy_name': strategy_name,
        'price': price_value,
        'is_stale': bool(is_stale),
        'vol_bias': vol_bias if vol_bias is not None else None,
        'proxy_note': proxy_note,
        'net_pl': net_pl,
        'pl_pct': pl_pct,
        'dte': dte,
        'action_code': action_code,
        'logic': logic,
        'sector': sector,
        'delta': strategy_delta,
        'is_hedge': is_hedge  # NEW
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
    traffic_jam_friction = context['traffic_jam_friction']

    all_position_reports = []
    total_net_pl = 0.0
    total_beta_delta = 0.0
    total_portfolio_theta = 0.0
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

        # Calculate theta and friction metrics
        for l in legs:
            leg_theta = parse_currency(l['Theta'])
            total_portfolio_theta += leg_theta
            total_abs_theta += abs(leg_theta)

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

    # Calculate Friction Horizon (Φ)
    friction_horizon_days = 0.0
    if total_abs_theta > 1.0:
        friction_horizon_days = total_liquidity_cost / total_abs_theta
    elif total_liquidity_cost > 0:
        friction_horizon_days = traffic_jam_friction  # Infinite friction (trapped)

    metrics: TriageMetrics = {
        'total_net_pl': total_net_pl,
        'total_beta_delta': total_beta_delta,
        'total_portfolio_theta': total_portfolio_theta,
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
        min_vol_bias=rules.get('vol_bias_threshold', 0.85),
        limit=20,
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
