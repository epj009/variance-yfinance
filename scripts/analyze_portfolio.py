import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional, Any

from get_market_data import get_market_data
from vol_screener import get_screener_results

# Import common utilities
try:
    from .common import map_sector_to_asset_class, warn_if_not_venv
    from .config_loader import load_trading_rules, load_market_config, load_strategies, DEFAULT_TRADING_RULES
    from .portfolio_parser import (
        PortfolioParser, parse_currency, parse_dte, get_root_symbol, is_stock_type
    )
    from .strategy_detector import identify_strategy, cluster_strategies, map_strategy_to_id
    from .triage_engine import triage_portfolio, get_position_aware_opportunities
except ImportError:
    # Fallback for direct script execution
    from common import map_sector_to_asset_class, warn_if_not_venv
    from config_loader import load_trading_rules, load_market_config, load_strategies, DEFAULT_TRADING_RULES
    from portfolio_parser import (
        PortfolioParser, parse_currency, parse_dte, get_root_symbol, is_stock_type
    )
    from strategy_detector import identify_strategy, cluster_strategies, map_strategy_to_id
    from triage_engine import triage_portfolio, get_position_aware_opportunities

# Load Configurations
RULES = load_trading_rules()
MARKET_CONFIG = load_market_config()
STRATEGIES = load_strategies()

# Constants
TRAFFIC_JAM_FRICTION = 99.9  # Sentinel value for infinite friction (trapped position)


def analyze_portfolio(file_path: str) -> Dict[str, Any]:
    """
    Main entry point for Portfolio Analysis (Portfolio Triage).

    Thin orchestrator that delegates to specialized modules:
    - portfolio_parser: CSV parsing
    - strategy_detector: Strategy identification
    - triage_engine: Position analysis and action detection
    """
    # Step 1: Parse CSV
    positions = PortfolioParser.parse(file_path)
    if not positions:
        return {"error": "No positions found in CSV or error parsing file."}

    # Step 2: Cluster Strategies
    clusters = cluster_strategies(positions)

    # Step 3: Fetch Market Data
    unique_roots = list(set(get_root_symbol(l['Symbol']) for l in positions))
    unique_roots = [r for r in unique_roots if r]  # Filter empty roots
    market_data = get_market_data(unique_roots)

    # Step 4: Data Freshness Check
    now = datetime.now()
    stale_count = sum(1 for d in market_data.values() if d.get('is_stale', False))
    widespread_staleness = len(market_data) > 0 and (stale_count / len(market_data)) > RULES['global_staleness_threshold']

    # Step 5a: First pass - Calculate portfolio-level metrics
    preliminary_context = {
        'market_data': market_data,
        'rules': RULES,
        'market_config': MARKET_CONFIG,
        'strategies': STRATEGIES,
        'traffic_jam_friction': TRAFFIC_JAM_FRICTION,
        'portfolio_beta_delta': 0.0,  # Placeholder for first pass
        'net_liquidity': RULES.get('net_liquidity', 50000.0) # Default
    }
    _, preliminary_metrics = triage_portfolio(clusters, preliminary_context)

    # Step 5b: Second pass - Use portfolio context for hedge detection
    triage_context = {
        'market_data': market_data,
        'rules': RULES,
        'market_config': MARKET_CONFIG,
        'strategies': STRATEGIES,
        'traffic_jam_friction': TRAFFIC_JAM_FRICTION,
        'portfolio_beta_delta': preliminary_metrics['total_beta_delta'],
        'net_liquidity': RULES.get('net_liquidity', 50000.0)
    }
    all_position_reports, metrics = triage_portfolio(clusters, triage_context)

    # Unpack metrics
    total_net_pl = metrics['total_net_pl']
    total_beta_delta = metrics['total_beta_delta']
    total_portfolio_theta = metrics['total_portfolio_theta']
    total_portfolio_theta_vrp_adj = metrics['total_portfolio_theta_vrp_adj']
    friction_horizon_days = metrics['friction_horizon_days']
    total_option_legs = metrics['total_option_legs']
    total_capital_at_risk = metrics['total_capital_at_risk']
    
    # --- Generate Structured Report Data ---
    report = {
        "analysis_time": now.strftime('%Y-%m-%d %H:%M:%S'),
        "data_freshness_warning": widespread_staleness,
        "market_data_symbols_count": len(unique_roots),
        "triage_actions": [],
        "portfolio_overview": [],
        "portfolio_summary": {
            "total_net_pl": total_net_pl,
            "total_beta_delta": total_beta_delta,
            "total_portfolio_theta": total_portfolio_theta,
            "total_portfolio_theta_vrp_adj": total_portfolio_theta_vrp_adj,
            "portfolio_vrp_markup": (total_portfolio_theta_vrp_adj / total_portfolio_theta - 1) if total_portfolio_theta != 0 else 0.0,
            "friction_horizon_days": friction_horizon_days,
            "theta_net_liquidity_pct": 0.0,
            "theta_vrp_net_liquidity_pct": 0.0,
            "delta_theta_ratio": 0.0,
            "bp_usage_pct": 0.0
        },
        "data_integrity_warning": {"risk": False, "details": ""},
        "delta_spectrograph": [],
        "sector_balance": [],
        "sector_concentration_warning": {"risk": False},
        "asset_mix": [],
        "asset_mix_warning": {"risk": False, "details": ""},
        "caution_items": [],
        "stress_box": None,
        "health_check": {
            "liquidity_warnings": []
        }
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
        if r['action_code']:
            entry["action_code"] = r['action_code']
            report['triage_actions'].append(entry)
        else:
            entry["action_code"] = None
            report['portfolio_overview'].append(entry)

    # Populate Portfolio Summary
    net_liq = RULES['net_liquidity']
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

    # Data Integrity Guardrail
    # Check if average theta per leg is suspiciously low (< 0.5), which indicates per-share Greeks bug
    # Threshold of 0.5 catches per-share bugs (0.02-0.15) while avoiding false positives on calendars/butterflies (0.75+)
    avg_theta_per_leg = abs(total_portfolio_theta) / total_option_legs if total_option_legs > 0 else 0
    if total_option_legs > 0 and avg_theta_per_leg < RULES['data_integrity_min_theta']:
        report['data_integrity_warning']['risk'] = True
        report['data_integrity_warning']['details'] = f"Average theta per leg ({avg_theta_per_leg:.2f}) is suspiciously low. Ensure your CSV contains TOTAL position values (Contract Qty * 100), not per-share Greeks. Risk metrics (Stress Box) may be understated by 100x."

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
        if pct > RULES['concentration_risk_pct']:
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

    if equity_pct > RULES['asset_mix_equity_threshold']:
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
    beta_sym = RULES.get('beta_weighted_symbol', 'SPY') # Default to SPY if missing
    beta_price = 0.0
    if beta_sym in market_data:
        beta_price = market_data[beta_sym].get('price', 0.0)
    else:
        try:
            beta_data = get_market_data([beta_sym])
            beta_price = beta_data.get(beta_sym, {}).get('price', 0.0)
        except Exception:
            pass
            
    if beta_price > 0:
        total_portfolio_vega = metrics.get('total_portfolio_vega', 0.0)
        scenarios = RULES.get('stress_scenarios', DEFAULT_TRADING_RULES['stress_scenarios'])
        stress_box_scenarios = []
        for s in scenarios:
            label = s['label']
            pct = s['move_pct']
            vol_move = s.get('vol_point_move', 0.0) # Absolute IV point change
            
            spy_points = beta_price * pct
            delta_pl = total_beta_delta * spy_points
            vega_pl = total_portfolio_vega * vol_move
            
            est_pl = delta_pl + vega_pl
            
            stress_box_scenarios.append({
                "label": label,
                "beta_move": spy_points,
                "est_pl": est_pl
            })
        report['stress_box'] = {
            "beta_symbol": beta_sym,
            "beta_price": beta_price,
            "total_portfolio_vega": total_portfolio_vega, # Expose for UI if needed
            "scenarios": stress_box_scenarios
        }

    # Step 6: Get Position-Aware Opportunities (vol screener with context)
    try:
        opportunities_data = get_position_aware_opportunities(
            positions=positions,
            clusters=clusters,
            net_liquidity=net_liq,
            rules=RULES
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

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Analyze current portfolio positions and generate a triage report.')
    parser.add_argument('file_path', type=str, help='Path to the portfolio CSV file.')
    
    args = parser.parse_args()
    
    warn_if_not_venv()
    report_data = analyze_portfolio(args.file_path)
    
    if "error" in report_data:
        print(json.dumps(report_data, indent=2), file=sys.stderr)
        sys.exit(1)

    print(json.dumps(report_data, indent=2))
