"""
Triage Engine Module

Handles position triage logic, action detection, and position classification.
Extracted from analyze_portfolio.py to improve maintainability.
"""

from datetime import datetime
from typing import Any, Optional, TypedDict

# Import common utilities
from .models.actions import ActionCommand, ActionFactory
from .portfolio_parser import (
    get_root_symbol,
    is_stock_type,
    parse_currency,
    parse_dte,
)
from .strategies.factory import StrategyFactory
from .strategy_detector import (
    identify_strategy,
    map_strategy_to_id,
)


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
    gamma: float  # NEW
    is_hedge: bool  # NEW: True if position is a structural hedge
    futures_multiplier_warning: Optional[str]


class TriageContext(TypedDict, total=False):
    """Type definition for triage context data."""

    market_data: dict[str, Any]
    rules: dict[str, Any]
    market_config: dict[str, Any]
    strategies: dict[str, Any]
    traffic_jam_friction: float
    portfolio_beta_delta: float  # NEW: Total portfolio delta for hedge validation
    net_liquidity: float  # NEW: For size threat checks


class TriageMetrics(TypedDict, total=False):
    """Type definition for portfolio-level triage metrics."""

    total_net_pl: float
    total_beta_delta: float
    total_portfolio_theta: float
    total_portfolio_theta_vrp_adj: float  # VRP-adjusted theta (quality-weighted)
    total_portfolio_vega: float
    total_portfolio_gamma: float  # NEW
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
    rules: dict[str, Any],
) -> bool:
    """
    Determine if a position qualifies as a structural portfolio hedge.
    """
    # Get hedge rules from config with safe defaults
    hedge_rules = rules.get("hedge_rules", {})

    # Check if hedge detection is enabled
    if not hedge_rules.get("enabled", False):
        return False

    # Default values if not in config
    index_symbols = hedge_rules.get("index_symbols", ["SPY", "QQQ", "IWM"])
    qualifying_strategies = hedge_rules.get(
        "qualifying_strategies", ["Long Put", "Vertical Spread (Put)"]
    )
    delta_threshold = hedge_rules.get("delta_threshold", -5)
    require_portfolio_long = hedge_rules.get("require_portfolio_long", True)

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
    root: str, beta_delta: float, market_config: dict[str, Any], rules: dict[str, Any]
) -> dict[str, Any]:
    """
    Validate that futures positions have plausible beta-weighted delta values.
    """
    result = {
        "is_futures": False,
        "multiplier": 1.0,
        "potential_issue": False,
        "expected_min": 0.0,
        "message": "",
    }

    # Only check symbols starting with '/'
    if not root.startswith("/"):
        return result

    result["is_futures"] = True

    # Get multiplier from config
    futures_multipliers = market_config.get("FUTURES_MULTIPLIERS", {})
    multiplier = futures_multipliers.get(root, 1.0)
    result["multiplier"] = multiplier

    # Get validation thresholds from rules
    validation_rules = rules.get("futures_delta_validation", {})
    if not validation_rules.get("enabled", True):
        return result

    min_delta_threshold = validation_rules.get("min_abs_delta_threshold", 1.0)
    result["expected_min"] = min_delta_threshold

    # Check if delta is suspiciously small for a futures position
    if abs(beta_delta) < min_delta_threshold and abs(beta_delta) > 0:
        result["potential_issue"] = True
        result["message"] = (
            f"Futures delta ({beta_delta:.2f}) appears unmultiplied. "
            f"Expected: delta x {multiplier} = {beta_delta * multiplier:.1f} SPY-eq. "
            f"Verify broker CSV contains beta-weighted values."
        )

    return result


def _beta_scale_from_deltas(leg: dict[str, Any]) -> Optional[float]:
    """
    Derive a beta-weighting scale from raw vs beta-weighted deltas.
    """
    raw_delta = parse_currency(leg.get("Delta", "0"))
    beta_delta = parse_currency(leg.get("beta_delta", "0"))
    if abs(raw_delta) < 1e-6 or abs(beta_delta) < 1e-6:
        return None
    return beta_delta / raw_delta


def _beta_weight_gamma(leg: dict[str, Any]) -> float:
    """
    Convert raw gamma to beta-weighted gamma when raw delta is available.
    """
    beta_gamma = parse_currency(leg.get("beta_gamma", "0"))
    if beta_gamma:
        return beta_gamma
    raw_gamma = parse_currency(leg.get("Gamma", "0"))
    scale = _beta_scale_from_deltas(leg)
    if scale is None:
        return raw_gamma
    return raw_gamma * (scale**2)


def calculate_days_held(legs: list[dict[str, Any]]) -> int:
    """
    Calculate the number of days the position has been held.
    """
    max_days = 0
    earliest_date = None

    for leg in legs:
        open_date_str = leg.get("Open Date")
        if not open_date_str:
            continue

        # Case 1: Raw numeric days (e.g. "12") or "12d" format
        clean_val = open_date_str.lower().replace("d", "").strip()
        if clean_val.isdigit():
            days = int(clean_val)
            if days > max_days:
                max_days = days
            continue

        # Case 2: Date string
        try:
            # Try flexible parsing
            for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d"):
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


def calculate_cluster_metrics(legs: list[dict[str, Any]], context: TriageContext) -> dict[str, Any]:
    """
    Step 1 of Triage: Calculate Greeks, stats, and identify strategy.
    """
    rules = context["rules"]
    market_config = context["market_config"]

    root = get_root_symbol(legs[0]["Symbol"])

    # Calculate DTE only for option legs
    option_legs = [leg for leg in legs if not is_stock_type(leg["Type"])]
    dtes = []
    for leg in option_legs:
        val = parse_dte(leg.get("DTE"))
        if val <= 0:
            # Fallback to Exp Date
            exp_str = leg.get("Exp Date")
            if exp_str:
                try:
                    exp_date = datetime.strptime(exp_str, "%Y-%m-%d").date()
                    val = (exp_date - datetime.now().date()).days
                except ValueError:
                    val = 0
        dtes.append(val)

    dte = min(dtes) if dtes else 0

    strategy_name = identify_strategy(legs)
    net_pl = sum(parse_currency(leg["P/L Open"]) for leg in legs)

    # Calculate net cost
    net_cost = sum(parse_currency(leg["Cost"]) for leg in legs)

    # Resolve Strategy ID
    strategy_id = map_strategy_to_id(strategy_name, net_cost)

    # --- Greek Aggregation ---
    strategy_delta = 0.0
    strategy_gamma = 0.0
    cluster_theta_raw = 0.0
    cluster_gamma_raw = 0.0
    futures_delta_warnings = []
    uses_raw_delta = False

    for leg in legs:
        b_delta_str = leg.get("beta_delta")
        if b_delta_str is None or str(b_delta_str).strip() == "":
            raw_delta_str = leg.get("Delta")
            if raw_delta_str and str(raw_delta_str).strip() != "":
                b_delta = parse_currency(raw_delta_str)
                uses_raw_delta = True
            else:
                b_delta = 0.0
        else:
            b_delta = parse_currency(b_delta_str)

        strategy_delta += b_delta

        leg_root = get_root_symbol(leg["Symbol"])
        futures_check = validate_futures_delta(
            root=leg_root, beta_delta=b_delta, market_config=market_config, rules=rules
        )
        if futures_check["potential_issue"]:
            futures_delta_warnings.append(futures_check["message"])

        b_gamma = _beta_weight_gamma(leg)
        strategy_gamma += b_gamma
        cluster_gamma_raw += parse_currency(leg.get("Gamma", "0"))
        cluster_theta_raw += parse_currency(leg.get("Theta", "0"))

    pl_pct = None
    if net_cost < 0:
        max_profit = abs(net_cost)
        if max_profit > 0:
            pl_pct = net_pl / max_profit
    elif net_cost > 0:
        pl_pct = net_pl / net_cost

    days_held = calculate_days_held(legs)

    # Retrieve live price for toxic theta calculations
    market_data = context.get("market_data", {})
    m_data = market_data.get(root, {})
    live_price_raw = m_data.get("price", 0)

    try:
        if hasattr(live_price_raw, "__len__") and not isinstance(live_price_raw, (str, bytes)):
            live_price = float(live_price_raw[0])
        else:
            live_price = float(live_price_raw)
    except (TypeError, ValueError, IndexError):
        live_price = 0.0

    price = (
        live_price if live_price > 0 else parse_currency(legs[0].get("Underlying Last Price", "0"))
    )

    return {
        "root": root,
        "strategy_name": strategy_name,
        "strategy_id": strategy_id,
        "dte": dte,
        "net_pl": net_pl,
        "net_cost": net_cost,
        "strategy_delta": strategy_delta,
        "strategy_gamma": strategy_gamma,
        "cluster_theta_raw": cluster_theta_raw,
        "cluster_gamma_raw": cluster_gamma_raw,
        "pl_pct": pl_pct,
        "days_held": days_held,
        "uses_raw_delta": uses_raw_delta,
        "futures_delta_warnings": futures_delta_warnings,
        "legs": legs,
        "price": price,
    }


def determine_cluster_action(metrics: dict[str, Any], context: TriageContext) -> TriageResult:
    """
    Step 2 of Triage: Determine Action Code using metrics and portfolio context.
    """
    market_data = context["market_data"]
    rules = context["rules"]
    net_liquidity = context.get("net_liquidity", 50000.0)

    # Unpack metrics
    root = metrics["root"]
    strategy_name = metrics["strategy_name"]
    strategy_id = metrics["strategy_id"]
    dte = metrics["dte"]
    net_pl = metrics["net_pl"]
    net_cost = metrics["net_cost"]
    strategy_delta = metrics["strategy_delta"]
    strategy_gamma = metrics["strategy_gamma"]
    pl_pct = metrics["pl_pct"]
    days_held = metrics["days_held"]
    uses_raw_delta = metrics["uses_raw_delta"]
    futures_delta_warnings = metrics["futures_delta_warnings"]
    legs = metrics["legs"]
    price = metrics["price"]

    strategies_config = context.get("strategies", {})
    strategy_obj = StrategyFactory.get_strategy(strategy_id, strategies_config, rules)

    cmd: Optional[ActionCommand] = None
    is_winner = False
    logic = ""

    # Retrieve live data
    m_data = market_data.get(root, {})
    is_stale = m_data.get("is_stale", False)
    vrp_structural = m_data.get("vrp_structural")
    proxy_note = m_data.get("proxy")
    sector = m_data.get("sector", "Unknown")

    if uses_raw_delta:
        logic = "Using unweighted Delta (Beta Delta missing)"

    # --- 0. Probabilistic Size Threat Check ---
    is_size_threat = False
    size_logic = ""

    beta_sym = rules.get("beta_weighted_symbol", "SPY")
    beta_data = market_data.get(beta_sym, {})
    beta_iv = beta_data.get("iv", 15.0)
    beta_price_raw = beta_data.get("price", 0.0)

    # Robust Type Handling: Ensure price is a float
    try:
        if hasattr(beta_price_raw, "__len__") and not isinstance(beta_price_raw, (str, bytes)):
            beta_price = float(beta_price_raw[0])
        else:
            beta_price = float(beta_price_raw)
    except (TypeError, ValueError, IndexError):
        beta_price = 0.0

    if beta_price > 0:
        em_1sd = beta_price * (beta_iv / 100.0 / 15.87)
        move_2sd = em_1sd * -2.0
        loss_at_2sd = (strategy_delta * move_2sd) + (0.5 * strategy_gamma * (move_2sd**2))

        size_threshold = net_liquidity * rules.get("size_threat_pct", 0.05)
        if abs(loss_at_2sd) > size_threshold and loss_at_2sd < 0:
            is_size_threat = True
            usage_pct = abs(loss_at_2sd) / net_liquidity
            size_logic = f"Tail Risk: {usage_pct:.1%} of Net Liq in -2SD move"

    # --- 0. Expiration Day Check ---
    if dte == 0:
        cmd = ActionFactory.create("EXPIRING", root, "Expiration Day - Manual Management Required")

    # --- 1. Harvest Logic (Delegated) ---
    if not cmd and net_cost < 0 and pl_pct is not None:
        cmd = strategy_obj.check_harvest(root, pl_pct, days_held)
        if cmd:
            is_winner = True

    if not is_winner and not cmd and is_size_threat:
        cmd = ActionFactory.create("SIZE_THREAT", root, size_logic if size_logic else "Excessive Position Size")

    # --- 2. Defense (Delegated) ---
    is_tested = strategy_obj.is_tested(legs, price)

    if not is_winner and not cmd and is_tested and dte < strategy_obj.gamma_trigger_dte:
        cmd = ActionFactory.create("DEFENSE", root, f"Tested & < {strategy_obj.gamma_trigger_dte} DTE")

    # --- 3. Gamma Zone ---
    if (
        not is_winner
        and not cmd
        and not is_tested
        and dte < strategy_obj.gamma_trigger_dte
        and dte > 0
    ):
        cmd = ActionFactory.create("GAMMA", root, f"< {strategy_obj.gamma_trigger_dte} DTE Risk")

    # --- 4. Hedge Detection ---
    is_hedge = detect_hedge_tag(
        root=root,
        strategy_name=strategy_name,
        strategy_delta=strategy_delta,
        portfolio_beta_delta=context.get("portfolio_beta_delta", 0.0),
        rules=rules,
    )

    # 4.5. Hedge Check
    if (
        is_hedge
        and not is_winner
        and not cmd
        and not is_tested
        and dte > strategy_obj.gamma_trigger_dte
    ):
        if (
            pl_pct is not None
            and rules["dead_money_pl_pct_low"] <= pl_pct <= rules["dead_money_pl_pct_high"]
        ) and (
            vrp_structural is not None
            and vrp_structural < rules["dead_money_vrp_structural_threshold"]
        ):
            cmd = ActionFactory.create("HEDGE_CHECK", root, f"Protective hedge on {root}. Review utility.")

    # --- 5. Toxic Theta (Delegated) ---
    if (
        (
            not is_winner
            and not cmd
            and not is_tested
            and dte > strategy_obj.gamma_trigger_dte
            and not is_hedge
        )
        and (
            pl_pct is not None
            and rules["dead_money_pl_pct_low"] <= pl_pct <= rules["dead_money_pl_pct_high"]
        )
        and net_cost < 0
    ):
        cmd = strategy_obj.check_toxic_theta(root, metrics, market_data)

    # --- 6. Earnings Check ---
    earnings_date = m_data.get("earnings_date")
    earnings_note = ""
    if earnings_date and earnings_date != "Unavailable":
        try:
            edate = datetime.fromisoformat(earnings_date).date()
            days_to_earn = (edate - datetime.now().date()).days
            if 0 <= days_to_earn <= rules["earnings_days_threshold"]:
                earnings_note = f"Earnings {days_to_earn}d"
                if strategy_obj.earnings_stance == "avoid":
                    if not cmd:
                        cmd = ActionFactory.create("EARNINGS_WARNING", root, "Binary Event Risk (Avoid)")
                    elif cmd.action_code == "HARVEST":
                        cmd = ActionFactory.create("HARVEST", root, f"{cmd.logic} | Close before Earnings!")
                elif strategy_obj.earnings_stance == "long_vol":
                    earnings_note = f"{earnings_note} (Play)"

                if cmd and "Earnings" not in cmd.logic:
                    cmd = ActionFactory.create(cmd.action_code, root, f"{cmd.logic} | {earnings_note}")
        except (ValueError, TypeError):
            pass

    # --- 7. VRP Momentum (SCALABLE) ---
    if not cmd and not is_tested and dte > strategy_obj.gamma_trigger_dte and not is_hedge:
        if pl_pct is not None and pl_pct < strategy_obj.profit_target_pct:
            vrp_s = m_data.get("vrp_structural", 0)
            vrp_t = m_data.get("vrp_tactical", 1.0)
            if vrp_s and vrp_t:
                markup = (vrp_t / vrp_s) - 1 if vrp_s != 0 else 0
                if markup > rules.get("vrp_momentum_threshold", 0.50):
                    cmd = ActionFactory.create("SCALABLE", root, f"VRP Surge: Tactical markup ({vrp_t:.2f}) is significantly above trend. High Alpha Opportunity.")

    # Finalize action_code and logic for the report
    action_code = cmd.action_code if cmd else None

    # If we have a command, use its logic. Otherwise, use accumulated metadata warnings.
    final_logic = cmd.logic if cmd else logic

    return {
        "root": root,
        "strategy_name": strategy_name,
        "price": price,
        "is_stale": is_stale,
        "vrp_structural": vrp_structural,
        "proxy_note": proxy_note,
        "net_pl": net_pl,
        "pl_pct": pl_pct,
        "dte": dte,
        "action_code": action_code,
        "logic": final_logic,
        "sector": sector,
        "delta": strategy_delta,
        "gamma": strategy_gamma,
        "is_hedge": is_hedge,
        "futures_multiplier_warning": (
            futures_delta_warnings[0] if futures_delta_warnings else None
        ),
    }


def triage_cluster(legs: list[dict[str, Any]], context: TriageContext) -> TriageResult:
    """
    Triage a single strategy cluster and determine action code.
    Backward-compatible entry point.
    """
    metrics = calculate_cluster_metrics(legs, context)
    return determine_cluster_action(metrics, context)


def triage_portfolio(
    clusters: list[list[dict[str, Any]]], context: TriageContext
) -> tuple[list[TriageResult], TriageMetrics]:
    """
    Triage all clusters in a portfolio and calculate portfolio-level metrics.
    """
    market_config = context["market_config"]
    rules = context["rules"]
    traffic_jam_friction = context["traffic_jam_friction"]

    all_cluster_metrics = []
    total_net_pl = 0.0
    total_beta_delta = 0.0
    total_portfolio_theta = 0.0
    total_portfolio_theta_vrp_adj = 0.0
    total_portfolio_vega = 0.0
    total_portfolio_gamma = 0.0
    total_liquidity_cost = 0.0
    total_abs_theta = 0.0
    total_option_legs = 0
    total_capital_at_risk = 0.0

    # PASS 1: Calculate metrics and accumulate portfolio-wide state
    for legs in clusters:
        if not legs:
            continue

        option_legs = [leg for leg in legs if not is_stock_type(leg["Type"])]
        total_option_legs += len(option_legs)

        # Step 1: Calculate cluster-level metrics
        m = calculate_cluster_metrics(legs, context)
        all_cluster_metrics.append(m)

        # Accumulate portfolio metrics
        total_net_pl += m["net_pl"]
        total_beta_delta += m["strategy_delta"]
        total_capital_at_risk += abs(m["net_cost"])

        # Aggregate Greeks and Friction
        for leg in legs:
            leg_theta = parse_currency(leg["Theta"])
            total_portfolio_theta += leg_theta
            total_abs_theta += abs(leg_theta)

            leg_vega = parse_currency(leg.get("Vega", "0"))
            total_portfolio_vega += leg_vega

            leg_gamma = _beta_weight_gamma(leg)
            total_portfolio_gamma += leg_gamma

            # Friction
            bid = parse_currency(leg["Bid"])
            ask = parse_currency(leg["Ask"])
            qty = abs(parse_currency(leg["Quantity"]))

            if ask > bid and qty > 0:
                spread = ask - bid
                multiplier = 100.0
                sym = leg["Symbol"].upper()
                futures_multipliers = market_config.get("FUTURES_MULTIPLIERS", {})
                if sym.startswith("/"):
                    if sym in futures_multipliers:
                        multiplier = futures_multipliers[sym]
                    else:
                        for future_prefix, future_mult in futures_multipliers.items():
                            if sym.startswith(future_prefix):
                                multiplier = future_mult
                                break
                total_liquidity_cost += spread * qty * multiplier

        # VRP Adjustment for portfolio theta
        m_data = context["market_data"].get(m["root"], {})
        vrp_t = m_data.get("vrp_tactical")

        if vrp_t is not None:
            vta_floor = rules.get("vrp_tactical_aggregation_floor", -0.50)
            vta_ceil = rules.get("vrp_tactical_aggregation_ceiling", 1.00)
            markup = vrp_t - 1.0
            clamped_markup = max(vta_floor, min(vta_ceil, markup))
            clamped_ratio = 1.0 + clamped_markup
            cluster_theta_vrp_adj = m["cluster_theta_raw"] * clamped_ratio
        else:
            vrp_s = m_data.get("vrp_structural", 1.0)
            cluster_theta_vrp_adj = m["cluster_theta_raw"] * vrp_s

        total_portfolio_theta_vrp_adj += cluster_theta_vrp_adj

    # PASS 2: Determine Action Codes with final portfolio delta
    final_context = context.copy()
    final_context["portfolio_beta_delta"] = total_beta_delta

    all_position_reports = []
    for m in all_cluster_metrics:
        report = determine_cluster_action(m, final_context)
        all_position_reports.append(report)

    # Calculate Friction Horizon (Φ)
    friction_horizon_days = 0.0
    if total_abs_theta > rules.get("friction_horizon_min_theta", 0.01):
        friction_horizon_days = total_liquidity_cost / total_abs_theta
    elif total_liquidity_cost > 0:
        friction_horizon_days = traffic_jam_friction

    metrics: TriageMetrics = {
        "total_net_pl": total_net_pl,
        "total_beta_delta": total_beta_delta,
        "total_portfolio_theta": total_portfolio_theta,
        "total_portfolio_theta_vrp_adj": total_portfolio_theta_vrp_adj,
        "total_portfolio_vega": total_portfolio_vega,
        "total_portfolio_gamma": total_portfolio_gamma,
        "total_liquidity_cost": total_liquidity_cost,
        "total_abs_theta": total_abs_theta,
        "total_option_legs": total_option_legs,
        "friction_horizon_days": friction_horizon_days,
        "total_capital_at_risk": total_capital_at_risk,
    }

    return all_position_reports, metrics


def get_position_aware_opportunities(
    positions: list[dict[str, Any]],
    clusters: list[list[dict[str, Any]]],
    net_liquidity: float,
    rules: dict[str, Any],
) -> dict[str, Any]:
    """
    Identifies concentrated vs. held positions and queries the vol screener.
    """
    from collections import defaultdict

    from .vol_screener import ScreenerConfig, screen_volatility

    # 1. Extract all unique roots
    held_roots = set()
    for pos in positions:
        root = get_root_symbol(pos.get("Symbol", ""))
        if root:
            held_roots.add(root)

    # 2. Calculate concentration per root
    root_clusters = defaultdict(list)
    for cluster in clusters:
        if cluster:
            root = get_root_symbol(cluster[0].get("Symbol", ""))
            if root:
                root_clusters[root].append(cluster)

    root_exposure = defaultdict(float)
    for pos in positions:
        root = get_root_symbol(pos.get("Symbol", ""))
        if root:
            cost_str = pos.get("Cost", "0")
            cost = abs(parse_currency(cost_str))
            root_exposure[root] += cost

    # 3. Apply Stacking Rule
    concentrated_roots_set = set()
    concentration_limit = net_liquidity * rules.get("concentration_limit_pct", 0.05)
    max_strategies = rules.get("max_strategies_per_symbol", 3)

    processed_groups = set()

    if not rules.get("allow_proxy_stacking", False):
        from .common import get_equivalent_exposures as _get_equiv
        get_equiv = _get_equiv
    else:
        def _local_fallback(symbol: str) -> set[str]:
            return {symbol}
        get_equiv = _local_fallback

    for root in held_roots:
        group_members = get_equiv(root)
        held_group_members = group_members & held_roots
        group_id = tuple(sorted(held_group_members))

        if group_id in processed_groups:
            continue
        processed_groups.add(group_id)

        exposure = sum(root_exposure.get(member, 0.0) for member in held_group_members)
        strategy_count = sum(len(root_clusters.get(member, [])) for member in held_group_members)

        if exposure > concentration_limit or strategy_count >= max_strategies:
            concentrated_roots_set.update(held_group_members)

    concentrated_roots = list(concentrated_roots_set)

    # 4. Call vol screener with position context
    screener_config = ScreenerConfig(
        exclude_symbols=concentrated_roots,
        held_symbols=list(held_roots),
        min_vrp_structural=rules.get("vrp_structural_threshold", 0.85),
        min_variance_score=rules.get("min_variance_score", 10.0),
        limit=None,
        allow_illiquid=False,
    )
    screener_results = screen_volatility(screener_config)

    # 5. Package results
    return {
        "meta": {
            "excluded_count": len(concentrated_roots),
            "excluded_symbols": concentrated_roots,
            "scan_timestamp": datetime.now().isoformat(),
        },
        "candidates": screener_results.get("candidates", []),
        "summary": screener_results.get("summary", {}),
    }
