"""
Triage Engine Module

Handles position triage logic, action detection, and position classification.
Extracted from analyze_portfolio.py to improve maintainability.
"""

from datetime import datetime
from typing import Any, Optional, TypedDict

import variance.triage.handlers  # noqa: F401
from variance.triage.chain import TriageChain
from variance.triage.request import TriageRequest

# Import common utilities
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
    tags: list[dict[str, Any]]
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


class TriageMetrics(TypedDict):
    """Type definition for portfolio-level triage metrics."""

    total_net_pl: float
    total_beta_delta: float
    total_portfolio_theta: float
    total_portfolio_theta_vrp_adj: float
    total_portfolio_vega: float
    total_portfolio_gamma: float
    total_liquidity_cost: float
    total_abs_theta: float
    total_option_legs: int
    friction_horizon_days: float
    total_capital_at_risk: float


def calculate_cluster_metrics(legs: list[dict[str, Any]], context: TriageContext) -> dict[str, Any]:
    """
    Step 1 of Triage: Calculate raw Greeks and P/L for a cluster.
    """
    market_data = context["market_data"]
    market_config = context["market_config"]
    rules = context["rules"]

    root = get_root_symbol(legs[0]["Symbol"])

    # Calculate DTE (Only for Options)
    dtes = []
    for leg in legs:
        l_type = str(leg.get("Type", "")).upper()
        if "OPTION" not in l_type:
            continue

        dte_val = parse_dte(leg.get("DTE"))
        if dte_val > 0:
            val = dte_val
        else:
            exp_str = leg.get("Exp Date")
            if not exp_str or exp_str == "None" or exp_str == "":
                val = 999
            else:
                try:
                    # Try ISO format: 2026-01-23
                    exp_date = datetime.strptime(str(exp_str), "%Y-%m-%d").date()
                    val = (exp_date - datetime.now().date()).days
                except ValueError:
                    try:
                        # Try Human formats: "Jan 23 2026" or "Jan 23, 2026"
                        clean_exp = str(exp_str).replace(",", "").strip()
                        exp_date = datetime.strptime(clean_exp, "%b %d %Y").date()
                        val = (exp_date - datetime.now().date()).days
                    except ValueError:
                        val = 999  # Data integrity fail fallback
        dtes.append(val)

    # Use 999 as sentinel for non-expiring/unknown
    dte = min(dtes) if dtes else 999

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
    Step 2 of Triage: Determine Action Code using Chain of Responsibility.
    """
    market_data = context["market_data"]
    rules = context["rules"]
    net_liquidity = context.get("net_liquidity", 50000.0)

    # Unpack metrics
    root = metrics["root"]
    strategy_id = metrics["strategy_id"]
    dte = metrics["dte"]
    net_pl = metrics["net_pl"]
    net_cost = metrics["net_cost"]
    strategy_delta = metrics["strategy_delta"]
    strategy_gamma = metrics["strategy_gamma"]
    pl_pct = metrics["pl_pct"]
    days_held = metrics["days_held"]
    legs = metrics["legs"]
    price = metrics["price"]

    # Retrieve live data
    m_data = market_data.get(root, {})
    is_stale = m_data.get("is_stale", False)
    vrp_structural = m_data.get("vrp_structural")
    vrp_tactical = m_data.get("vrp_tactical")
    proxy_note = m_data.get("proxy")
    sector = m_data.get("sector", "Unknown")
    earnings_date = m_data.get("earnings_date")
    hv20 = m_data.get("hv20")
    hv252 = m_data.get("hv252")

    # --- Phase 2: Strategy Pattern Delegation ---
    strategies_config = context.get("strategies", {})
    strategy_obj = StrategyFactory.get_strategy(strategy_id, strategies_config, rules)

    beta_symbol = rules.get("beta_weighted_symbol", "SPY")
    beta_price_raw = market_data.get(beta_symbol, {}).get("price", 0.0)
    try:
        if hasattr(beta_price_raw, "__len__") and not isinstance(beta_price_raw, (str, bytes)):
            beta_price = float(beta_price_raw[0])
        else:
            beta_price = float(beta_price_raw)
    except (TypeError, ValueError, IndexError):
        beta_price = None
    beta_iv_raw = market_data.get(beta_symbol, {}).get("iv")
    try:
        beta_iv = float(beta_iv_raw) if beta_iv_raw is not None else None
    except (TypeError, ValueError):
        beta_iv = None

    # Build Immutable Request
    request = TriageRequest(
        root=root,
        strategy_name=metrics["strategy_name"],
        strategy_id=strategy_id,
        dte=dte,
        net_pl=net_pl,
        net_cost=net_cost,
        strategy_delta=strategy_delta,
        strategy_gamma=strategy_gamma,
        pl_pct=pl_pct,
        days_held=days_held,
        price=price,
        legs=tuple(legs),
        vrp_structural=vrp_structural,
        vrp_tactical=vrp_tactical,
        is_stale=is_stale,
        sector=sector,
        earnings_date=earnings_date,
        portfolio_beta_delta=context.get("portfolio_beta_delta", 0.0),
        net_liquidity=net_liquidity,
        strategy_obj=strategy_obj,
        cluster_theta_raw=metrics.get("cluster_theta_raw", 0.0),
        cluster_gamma_raw=metrics.get("cluster_gamma_raw", 0.0),
        hv20=hv20,
        hv252=hv252,
        beta_symbol=beta_symbol,
        beta_price=beta_price,
        beta_iv=beta_iv,
    )

    # Execute deterministic chain
    chain = TriageChain(rules)
    final_request = chain.triage(request)

    # Extract Primary Action
    primary = final_request.primary_action
    action_code = primary.tag_type if primary else None

    # Logic accumulation
    logic = ""
    if metrics.get("uses_raw_delta"):
        logic = "Using unweighted Delta (Beta Delta missing)"

    # Badge Injection (Strategic Visibility)
    icon_map = {
        "HARVEST": "💰",
        "DEFENSE": "🛡️",
        "GAMMA": "☢️",
        "EXPIRING": "⏳",
        "TOXIC": "💀",
        "SCALABLE": "➕",
    }
    badge = f"[{icon_map.get(action_code, '•')} {action_code}] " if action_code else ""
    final_logic = badge + (primary.logic if primary else logic)
    if primary:
        earnings_notes = [t.logic for t in final_request.tags if t.tag_type == "EARNINGS_WARNING"]
        if earnings_notes and primary.tag_type != "EARNINGS_WARNING":
            final_logic = f"{final_logic} | {'; '.join(earnings_notes)}"

    return {
        "root": root,
        "strategy_name": metrics["strategy_name"],
        "price": price,
        "is_stale": is_stale,
        "vrp_structural": vrp_structural,
        "proxy_note": proxy_note,
        "net_pl": net_pl,
        "pl_pct": pl_pct,
        "dte": dte,
        "action_code": action_code,
        "logic": final_logic,
        "tags": [
            {"type": t.tag_type, "priority": t.priority, "logic": t.logic}
            for t in final_request.tags
        ],
        "sector": sector,
        "delta": strategy_delta,
        "gamma": strategy_gamma,
        "is_hedge": detect_hedge_tag(
            root=root,
            strategy_name=metrics["strategy_name"],
            strategy_delta=strategy_delta,
            portfolio_beta_delta=context.get("portfolio_beta_delta", 0.0),
            rules=rules,
        ),
        "futures_multiplier_warning": (
            metrics["futures_delta_warnings"][0] if metrics.get("futures_delta_warnings") else None
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
            # Use raw tactical markup without clamping
            markup = vrp_t - 1.0
            ratio = 1.0 + markup
            cluster_theta_vrp_adj = m["cluster_theta_raw"] * ratio
        else:
            vrp_s = m_data.get("vrp_structural")
            vrp_ratio = vrp_s if isinstance(vrp_s, (int, float)) else 1.0
            cluster_theta_vrp_adj = m["cluster_theta_raw"] * vrp_ratio

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
    market_data: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """
    Identifies concentrated vs. held positions and queries the vol screener.
    """
    from collections import defaultdict

    import numpy as np

    from .models.correlation import CorrelationEngine
    from .vol_screener import ScreenerConfig, screen_volatility

    # 1. Extract all unique roots
    held_roots = set()
    for pos in positions:
        root = get_root_symbol(pos.get("Symbol", ""))
        if root:
            held_roots.add(root)

    # 2. Calculate portfolio proxy returns (RFC 013)
    portfolio_returns_list = []
    if market_data:
        for root in held_roots:
            m_data = market_data.get(root, {})
            ret = m_data.get("returns")
            if ret:
                portfolio_returns_list.append(np.array(ret))

    proxy_returns = CorrelationEngine.get_portfolio_proxy_returns(portfolio_returns_list)

    # 3. Calculate concentration per root
    root_clusters = defaultdict(list)
    for cluster in clusters:
        if cluster:
            root = get_root_symbol(cluster[0].get("Symbol", ""))
            if root:
                root_clusters[root].append(cluster)

    root_exposure: defaultdict[str, float] = defaultdict(float)
    for pos in positions:
        root = get_root_symbol(pos.get("Symbol", ""))
        if root:
            cost_str = pos.get("Cost", "0")
            cost = abs(parse_currency(cost_str))
            root_exposure[root] += cost

    # 4. Apply Stacking Rule
    concentrated_roots_set = set()
    concentration_limit = net_liquidity * rules.get("concentration_limit_pct", 0.05)
    max_strategies = rules.get("max_strategies_per_symbol", 3)

    processed_groups = set()

    if not rules.get("allow_proxy_stacking", False):
        try:
            from .common import get_equivalent_exposures as _get_equiv

            get_equiv = _get_equiv
        except ImportError:

            def _local_fallback(symbol: str) -> set[str]:
                return {symbol}

            get_equiv = _local_fallback
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

    # 5. Call vol screener with position context and portfolio returns
    screener_config = ScreenerConfig(
        exclude_symbols=concentrated_roots,
        held_symbols=list(held_roots),
        min_vrp_structural=rules.get("vrp_structural_threshold", 0.85),
        min_variance_score=rules.get("min_variance_score", 10.0),
        min_iv_percentile=rules.get("min_iv_percentile", 0.0),
        limit=None,
        allow_illiquid=False,
    )
    screener_results = screen_volatility(
        screener_config, portfolio_returns=proxy_returns if len(proxy_returns) > 0 else None
    )

    # 6. Package results
    return {
        "meta": {
            "excluded_count": len(concentrated_roots),
            "excluded_symbols": concentrated_roots,
            "scan_timestamp": datetime.now().isoformat(),
        },
        "candidates": screener_results.get("candidates", []),
        "summary": screener_results.get("summary", {}),
    }


def validate_futures_delta(
    root: str, beta_delta: float, market_config: dict[str, Any], rules: dict[str, Any]
) -> dict[str, Any]:
    """
    Check if a futures position has potentially unmultiplied beta-weighted delta.
    """
    val_config = rules.get("futures_delta_validation", {})
    if not val_config.get("enabled", True):
        return {
            "is_futures": root.startswith("/"),
            "potential_issue": False,
            "message": "",
            "multiplier": None,
        }

    futures_multipliers = market_config.get("FUTURES_MULTIPLIERS", {})
    is_future = root.startswith("/")
    multiplier = futures_multipliers.get(root)
    # If it starts with / but isn't in multipliers, check if any multiplier key is a prefix
    if not is_future:
        for prefix in futures_multipliers:
            if root.startswith(prefix):
                is_future = True
                multiplier = futures_multipliers.get(prefix)
                break

    threshold = val_config.get("min_abs_delta_threshold", 1.0)
    if is_future:
        if 0 < abs(beta_delta) < threshold:
            return {
                "is_futures": True,
                "potential_issue": True,
                "message": f"Low Beta Delta ({beta_delta:.2f}) for future {root}; likely unmultiplied; check multiplier.",
                "multiplier": multiplier,
                "expected_min": threshold,
            }

    return {
        "is_futures": is_future,
        "potential_issue": False,
        "message": "",
        "multiplier": multiplier,
        "expected_min": threshold if is_future else None,
    }


def detect_hedge_tag(
    root: str,
    strategy_name: str,
    strategy_delta: float,
    portfolio_beta_delta: float,
    rules: dict[str, Any],
) -> bool:
    """
    Detect if a position is serving as a structural portfolio hedge.
    """
    hedge_rules = rules.get("hedge_rules", {})
    if not hedge_rules.get("enabled", True):
        return False

    # 1. Is it an index?
    if root.upper() not in hedge_rules.get("index_symbols", []):
        return False

    # 2. Is it a qualifying strategy?
    if strategy_name not in hedge_rules.get("qualifying_strategies", []):
        return False

    # 3. Does it have significant negative delta?
    if strategy_delta > hedge_rules.get("delta_threshold", -5):
        return False

    # 4. Does the portfolio actually need a hedge?
    if hedge_rules.get("require_portfolio_long", True) and portfolio_beta_delta < 0:
        return False

    return True


def _beta_weight_gamma(leg: dict[str, Any]) -> float:
    """Calculates beta-weighted gamma for a single leg."""
    gamma = parse_currency(leg.get("Gamma", "0"))
    beta_gamma = leg.get("beta_gamma")
    if beta_gamma is not None and str(beta_gamma).strip() != "":
        return parse_currency(beta_gamma)
    b_delta_str = leg.get("beta_delta")
    raw_delta_str = leg.get("Delta")

    if b_delta_str and raw_delta_str:
        b_delta = parse_currency(b_delta_str)
        raw_delta = parse_currency(raw_delta_str)
        if abs(raw_delta) > 0.001:
            beta = b_delta / raw_delta
            # Gamma scales by beta squared
            return gamma * (beta**2)

    return gamma


def calculate_days_held(legs: list[dict[str, Any]]) -> int:
    """Calculates the minimum days a cluster has been held."""
    days = []
    for leg in legs:
        open_date_str = leg.get("Open Date")
        if open_date_str:
            try:
                # Handle Tastytrade format or simple ISO
                if " " in open_date_str:
                    # e.g. "Dec 20 2025"
                    open_date = datetime.strptime(open_date_str, "%b %d %Y").date()
                else:
                    open_date = datetime.fromisoformat(open_date_str).date()
                days.append((datetime.now().date() - open_date).days)
            except (ValueError, TypeError):
                pass
    return min(days) if days else 0
