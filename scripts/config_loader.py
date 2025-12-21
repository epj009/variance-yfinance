"""
Centralized configuration loading for Variance.
Handles all config files with graceful fallbacks.
"""

import json
import sys
from typing import Dict, Any

# Consolidated defaults (Union of analyze_portfolio and vol_screener defaults)
DEFAULT_TRADING_RULES: Dict[str, Any] = {
    # Triage / Analyzer Defaults
    "vrp_structural_threshold": 0.85,
    "dead_money_vrp_structural_threshold": 0.80,
    "dead_money_pl_pct_low": -0.10,
    "dead_money_pl_pct_high": 0.10,
    "low_ivr_threshold": 20,
    "gamma_dte_threshold": 21,
    "profit_harvest_pct": 0.50,
    "earnings_days_threshold": 5,
    "portfolio_delta_long_threshold": 75,
    "portfolio_delta_short_threshold": -50,
    "concentration_risk_pct": 0.25,
    "net_liquidity": 50000,
    "theta_efficiency_low": 0.1,
    "theta_efficiency_high": 0.5,
    "beta_weighted_symbol": "SPY",
    "global_staleness_threshold": 0.50,
    "data_integrity_min_theta": 0.50,
    "asset_mix_equity_threshold": 0.80,
    "stress_scenarios": [
        {"label": "Crash (-5%)", "move_pct": -0.05},
        {"label": "Dip (-3%)", "move_pct": -0.03},
        {"label": "Flat", "move_pct": 0.0},
        {"label": "Rally (+3%)", "move_pct": 0.03},
        {"label": "Rally (+5%)", "move_pct": 0.05}
    ],
    # Screener Defaults
    "min_atm_volume": 500,
    "max_slippage_pct": 0.05,
    "bats_efficiency_min_price": 15,
    "bats_efficiency_max_price": 75,
    "bats_efficiency_vrp_structural": 1.0,
}


def load_trading_rules() -> Dict[str, Any]:
    """
    Loads 'config/trading_rules.json' and merges it with DEFAULT_TRADING_RULES.
    Returns the merged dictionary. Handles FileNotFoundError by returning defaults + warning.
    """
    try:
        with open('config/trading_rules.json', 'r') as f:
            return {**DEFAULT_TRADING_RULES, **json.load(f)}
    except FileNotFoundError:
        print("Warning: config/trading_rules.json not found. Using defaults.", file=sys.stderr)
        return DEFAULT_TRADING_RULES.copy()
    except json.JSONDecodeError as e:
        print(f"Warning: config/trading_rules.json is malformed ({e}). Using defaults.", file=sys.stderr)
        return DEFAULT_TRADING_RULES.copy()


def load_market_config() -> Dict[str, Any]:
    """
    Loads 'config/market_config.json'.
    Returns the dictionary or empty dict if not found (with warning).
    """
    try:
        with open('config/market_config.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print("Warning: config/market_config.json not found.", file=sys.stderr)
        return {}
    except json.JSONDecodeError as e:
        print(f"Warning: config/market_config.json is malformed ({e}).", file=sys.stderr)
        return {}


def load_system_config() -> Dict[str, Any]:
    """
    Loads 'config/system_config.json'.
    Returns the dictionary or empty dict if not found (with warning).
    """
    try:
        with open('config/system_config.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print("Warning: config/system_config.json not found. Using defaults.", file=sys.stderr)
        return {}
    except json.JSONDecodeError as e:
        print(f"Warning: config/system_config.json is malformed ({e}). Using defaults.", file=sys.stderr)
        return {}


def load_strategies() -> Dict[str, Dict[str, Any]]:
    """
    Unified entry point for strategies.
    Delegates to scripts.strategy_loader.load_strategies().
    """
    try:
        from .strategy_loader import load_strategies as _load_strategies
    except ImportError:
        from strategy_loader import load_strategies as _load_strategies

    return _load_strategies()
