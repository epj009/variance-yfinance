import argparse
import json
import math
import sys
from collections import defaultdict
from datetime import datetime
from typing import Any, Optional

# Import common utilities
from .common import map_sector_to_asset_class, warn_if_not_venv
from .config_loader import load_config_bundle
from .get_market_data import MarketDataFactory
from .portfolio_parser import (
    PortfolioParser,
    get_root_symbol,
)
from .strategy_detector import cluster_strategies
from .triage_engine import get_position_aware_opportunities, triage_portfolio

# Constants
TRAFFIC_JAM_FRICTION = 99.9  # Sentinel value for infinite friction (trapped position)

from .models import Portfolio, Position, StrategyCluster


def analyze_portfolio(
    file_path: str,
    *,
    config: Optional[dict[str, Any]] = None,
    config_dir: Optional[str] = None,
    strict: Optional[bool] = None,
) -> dict[str, Any]:
    """
    Main entry point for Portfolio Analysis (Portfolio Triage).
    """
    if config is None:
        config = load_config_bundle(config_dir=config_dir, strict=strict)

    rules = config.get("trading_rules", {})
    market_config = config.get("market_config", {})
    strategies = config.get("strategies", {})

    # Step 1: Parse CSV
    raw_positions = PortfolioParser.parse(file_path)
    if not raw_positions:
        return {"error": "No positions found in CSV or error parsing file."}

    # Step 2: Create Domain Objects
    positions = [Position.from_row(row) for row in raw_positions]
    
    # Step 3: Fetch Market Data
    unique_roots = list(set(pos.root_symbol for pos in positions))
    unique_roots = [r for r in unique_roots if r]

    beta_sym = rules.get("beta_weighted_symbol", "SPY")
    if beta_sym not in unique_roots:
        unique_roots.append(beta_sym)

    provider = MarketDataFactory.get_provider()
    market_data = provider.get_market_data(unique_roots)

    # Step 3b: Beta Data Hard Gate
    beta_entry = market_data.get(beta_sym, {})
    beta_price = beta_entry.get("price", 0)

    if hasattr(beta_price, "__len__") and not isinstance(beta_price, (str, bytes)):
        beta_price = float(beta_price[0])
    else:
        beta_price = float(beta_price)

    if not beta_entry or beta_price <= 0:
        return {
            "error": f"CRITICAL: Beta weighting source ({beta_sym}) unavailable. Risk analysis halted.",
            "details": "Check internet connection or data provider status.",
        }

    # Step 4: Cluster Strategies (Using raw positions for now, to keep existing logic)
    raw_clusters = cluster_strategies(raw_positions)
    
    # Convert to Domain Clusters
    domain_clusters = []
    for raw_cluster in raw_clusters:
        cluster_positions = [Position.from_row(row) for row in raw_cluster]
        domain_clusters.append(StrategyCluster(legs=cluster_positions))

    # Initialize Portfolio Object
    portfolio = Portfolio(clusters=domain_clusters, net_liquidity=rules.get("net_liquidity", 50000.0), rules=rules)

    now = datetime.now()
    # Execute single-pass triage
    triage_context = {
        "market_data": market_data,
        "rules": rules,
        "market_config": market_config,
        "strategies": strategies,
        "traffic_jam_friction": TRAFFIC_JAM_FRICTION,
        "net_liquidity": portfolio.net_liquidity,
    }
    all_position_reports, metrics = triage_portfolio(raw_clusters, triage_context)

    # Unpack metrics
    total_net_pl = metrics["total_net_pl"]
    total_beta_delta = metrics["total_beta_delta"]
    total_portfolio_theta = metrics["total_portfolio_theta"]
    total_portfolio_theta_vrp_adj = metrics["total_portfolio_theta_vrp_adj"]
    friction_horizon_days = metrics["friction_horizon_days"]
    total_capital_at_risk = metrics["total_capital_at_risk"]

    # --- Generate Structured Report Data ---
    report = {
        "analysis_time": now.strftime("%Y-%m-%d %H:%M:%S"),
        "market_data_symbols_count": len(unique_roots),
        "triage_actions": [],
        "portfolio_overview": [],
        "portfolio_summary": {
            "total_net_pl": total_net_pl,
            "total_beta_delta": total_beta_delta,
            "total_portfolio_theta": total_portfolio_theta,
            "total_portfolio_theta_vrp_adj": total_portfolio_theta_vrp_adj,
            "portfolio_vrp_markup": (total_portfolio_theta_vrp_adj / total_portfolio_theta - 1)
            if total_portfolio_theta != 0
            else 0.0,
            "friction_horizon_days": friction_horizon_days,
            "theta_net_liquidity_pct": 0.0,
            "theta_vrp_net_liquidity_pct": 0.0,
            "delta_theta_ratio": 0.0,
            "bp_usage_pct": 0.0,
        },
        "delta_spectrograph": [],
        "sector_balance": [],
        "sector_concentration_warning": {"risk": False},
        "asset_mix": [],
        "asset_mix_warning": {"risk": False, "details": ""},
        "caution_items": [],
        "stress_box": None,
        "health_check": {"liquidity_warnings": []},
    }

    # Populate Triage Actions
    for r in all_position_reports:
        entry = {
            "symbol": r['root'],
            "strategy": r['strategy_name'],
            "price": r['price'],
            "is_stale": r['is_stale'],
            "vrp_structural": r['vrp_structural'],
            "proxy_note": r['proxy_note'],
            "net_pl": r['net_pl'],
            "pl_pct": r['pl_pct'],
            "dte": r['dte'],
            "logic": r['logic'],
            "sector": r['sector'],
            "is_hedge": r.get('is_hedge', False)
        }

        # HEDGE PRIORITY: Always force hedges into the Action Required list
        # to ensure they are audited for utility regularly.
        if r.get('is_hedge') and not r.get('action_code'):
            entry["action_code"] = "HEDGE_CHECK"
            report['triage_actions'].append(entry)
        elif r.get('action_code'):
            entry["action_code"] = r['action_code']
            report['triage_actions'].append(entry)
        else:
            entry["action_code"] = None
            report['portfolio_overview'].append(entry)

    # Step 7: Finalize Portfolio Summary and Report
    net_liq = rules['net_liquidity']
    report['portfolio_summary']['net_liquidity'] = net_liq

    if net_liq > 0:
        theta_as_pct_of_nl = total_portfolio_theta / net_liq
        theta_vrp_as_pct_of_nl = total_portfolio_theta_vrp_adj / net_liq
        report['portfolio_summary']['theta_net_liquidity_pct'] = theta_as_pct_of_nl
        report['portfolio_summary']['theta_vrp_net_liquidity_pct'] = theta_vrp_as_pct_of_nl

        # Calculate BP Usage % (store as decimal ratio, not percentage)
        bp_usage_pct = total_capital_at_risk / net_liq
        report['portfolio_summary']['bp_usage_pct'] = bp_usage_pct

    # Delta/Theta Ratio (use VRP-adjusted theta for more accurate stability measure)
    if total_portfolio_theta_vrp_adj != 0:
        report['portfolio_summary']['delta_theta_ratio'] = total_beta_delta / total_portfolio_theta_vrp_adj
    else:
        report['portfolio_summary']['delta_theta_ratio'] = 0.0

    # Populate Delta Spectrograph
    root_deltas = defaultdict(float)
    for r in all_position_reports:
        root_deltas[r['root']] += r['delta']
    sorted_deltas = sorted(root_deltas.items(), key=lambda x: abs(x[1]), reverse=True)
    for root, delta in sorted_deltas[:10]:
        report['delta_spectrograph'].append({
            "symbol": root,
            "delta": delta
        })

    # Populate Sector Balance
    sector_counts = defaultdict(int)
    for r in all_position_reports:
        sector_counts[r['sector']] += 1
    total_positions = len(all_position_reports)
    sorted_sectors = sorted(sector_counts.items(), key=lambda x: x[1], reverse=True)
    for sec, count in sorted_sectors:
        pct = count / total_positions if total_positions > 0 else 0
        report['sector_balance'].append({
            "sector": sec,
            "count": count,
            "percentage": pct
        })

    concentrations = []
    for sec, count in sorted_sectors:
        pct = count / total_positions if total_positions > 0 else 0
        if pct > rules['concentration_risk_pct']:
            concentrations.append(f"{sec} ({count} pos, {pct:.0%})")
    if concentrations:
        report['sector_concentration_warning'] = {
            "risk": True,
            "details": f"High exposure to {', '.join(concentrations)}."
        }
    else:
        report['sector_concentration_warning'] = {"risk": False}

    # Calculate Asset Mix (Equity, Commodity, Fixed Income, FX, Index)
    asset_class_counts = defaultdict(int)
    for r in all_position_reports:
        asset_class = map_sector_to_asset_class(r['sector'])
        asset_class_counts[asset_class] += 1

    # Build asset_mix dictionary with percentages
    for asset_class, count in asset_class_counts.items():
        pct = count / total_positions if total_positions > 0 else 0
        report['asset_mix'].append({
            "asset_class": asset_class,
            "count": count,
            "percentage": pct  # Store as float for programmatic use
        })

    # Sort by count descending
    report['asset_mix'].sort(key=lambda x: x['count'], reverse=True)

    # Check for Equity Heavy (> 80%)
    equity_pct = 0.0
    for item in report['asset_mix']:
        if item['asset_class'] == 'Equity':
            equity_pct = item['percentage']
            break

    if equity_pct > rules['asset_mix_equity_threshold']:
        report['asset_mix_warning'] = {
            "risk": True,
            "details": f"Equity exposure is {equity_pct:.0%}. Portfolio is correlation-heavy. Consider adding Commodities, FX, or Fixed Income."
        }
    else:
        report['asset_mix_warning'] = {"risk": False}

    # Populate Caution Items
    for r in all_position_reports:
        if "stale" in r['logic'].lower():
            report['caution_items'].append(f"{r['root']}: price stale/absent; tested status uncertain")
        if r.get('action_code') == "EARNINGS_WARNING" or "Binary Event" in r.get('logic', ""):
            report['caution_items'].append(f"{r['root']}: earnings soon (see action/logic)")

    # Stress Box (Scenario Simulator)
    beta_sym = rules.get('beta_weighted_symbol', 'SPY') # Default to SPY if missing
    # Retrieve Beta Price for Stress Testing
    beta_price_raw = market_data.get(beta_sym, {}).get('price', 0.0)

    # Robust Type Handling: Ensure price is a float
    try:
        if hasattr(beta_price_raw, '__len__') and not isinstance(beta_price_raw, (str, bytes)):
            beta_price = float(beta_price_raw[0])
        else:
            beta_price = float(beta_price_raw)
    except (TypeError, ValueError, IndexError):
        beta_price = 0.0

    if beta_price > 0:
        # Get Beta (SPY) IV for Expected Move calculation
        beta_iv = market_data.get(beta_sym, {}).get('iv', 15.0) # Default to 15% if missing

        # 1-Day Expected Move (1SD) = Price * (IV / sqrt(252))
        em_1sd = beta_price * (beta_iv / 100.0 / math.sqrt(252))

        # Dynamic Stress Scenarios from Config
        stress_config = rules.get('stress_scenarios', [])

        # Fallback if config is missing scenarios
        if not stress_config:
            stress_config = [
                {"label": "Tail Risk (2SD-)", "move_pct": None, "sigma": -2.0, "vol_point_move": 10.0},
                {"label": "Flat", "move_pct": 0.0, "vol_point_move": 0.0},
                {"label": "Tail Risk (2SD+)", "move_pct": None, "sigma": 2.0, "vol_point_move": -10.0}
            ]

        stress_box_scenarios = []
        for s in stress_config:
            label = s.get('label', 'Scenario')
            vol_move = s.get('vol_point_move', 0.0)

            # Calculate Beta Move (Price Change in SPY-equivalent terms)
            if s.get('move_pct') is not None:
                move_points = beta_price * s['move_pct']
                sigma = move_points / em_1sd if em_1sd != 0 else 0.0
            elif s.get('sigma') is not None:
                sigma = s['sigma']
                move_points = em_1sd * sigma
            else:
                move_points = 0.0
                sigma = 0.0

            # --- Per-Position P/L Calculation ---
            total_est_pl = 0.0
            total_drift = 0.0

            for pos_report in all_position_reports:
                # Get required values from the report, with safe defaults
                pos_beta_delta = pos_report.get('delta', 0.0)
                # FIX: Use 'gamma' (beta-weighted) directly, as 'raw_gamma' is not passed by triage_engine
                pos_beta_gamma = pos_report.get('gamma', 0.0)

                pos_raw_vega = pos_report.get('raw_vega', 0.0)
                pos_beta = pos_report.get('beta', 1.0)

                # 1. Delta P/L: Uses beta-weighted delta against the SPY move
                delta_pl = pos_beta_delta * move_points

                # 2. Gamma P/L: Uses beta-weighted gamma and SPY move
                #    P/L = 0.5 * Gamma_BW * (Move_SPY)^2
                gamma_pl = 0.5 * pos_beta_gamma * (move_points ** 2)

                # 3. Vega P/L: Uses raw vega and a beta-scaled volatility move
                #    This is an approximation, assuming vol-beta is similar to price-beta.
                vega_pl = (pos_raw_vega * pos_beta) * vol_move

                total_est_pl += (delta_pl + gamma_pl + vega_pl)

                # Delta Drift = Gamma_BW * Move_SPY
                total_drift += pos_beta_gamma * move_points

            new_delta = total_beta_delta + total_drift

            stress_box_scenarios.append({
                "label": label,
                "beta_move": move_points,
                "est_pl": total_est_pl,
                "sigma": sigma,
                "drift": total_drift,
                "new_delta": new_delta
            })

        report['stress_box'] = {
            "beta_symbol": beta_sym,
            "beta_price": beta_price,
            "beta_iv": beta_iv,
            "em_1sd": em_1sd,
            "scenarios": stress_box_scenarios
        }

    # Step 7: Finalize Portfolio Summary Metrics (Post-calculations)
    # Extract Tail Risk (Worst Case Scenario)
    total_tail_risk = 0.0
    if report.get('stress_box'):
        scenarios = report['stress_box']['scenarios']
        # Find the scenario with the largest loss (most negative est_pl)
        worst_case_pl = min((s['est_pl'] for s in scenarios), default=0.0)
        if worst_case_pl < 0:
            total_tail_risk = abs(worst_case_pl)

    report['portfolio_summary']['total_tail_risk'] = total_tail_risk
    report['portfolio_summary']['tail_risk_pct'] = (total_tail_risk / net_liq) if net_liq > 0 else 0.0

    # Step 8: Get Position-Aware Opportunities (vol screener with context)
    try:
        opportunities_data = get_position_aware_opportunities(
            positions=raw_positions,
            clusters=raw_clusters,
            net_liquidity=net_liq,
            rules=rules
        )
        report['opportunities'] = opportunities_data
    except Exception as e:
        # Graceful degradation: If screener fails, add empty opportunities section
        report['opportunities'] = {
            "meta": {
                "excluded_count": 0,
                "excluded_symbols": [],
                "scan_timestamp": datetime.now().isoformat(),
                "error": str(e)
            },
            "candidates": [],
            "summary": {}
        }

    # Step 7: Return Complete Report
    return report

def main():
    parser = argparse.ArgumentParser(description='Analyze current portfolio positions and generate a triage report.')
    parser.add_argument('file_path', type=str, help='Path to the portfolio CSV file.')

    args = parser.parse_args()

    warn_if_not_venv()
    report_data = analyze_portfolio(args.file_path)

    if "error" in report_data:
        print(json.dumps(report_data, indent=2), file=sys.stderr)
        sys.exit(1)

    print(json.dumps(report_data, indent=2))

if __name__ == "__main__":
    main()
