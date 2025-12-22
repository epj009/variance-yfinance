import os
import sys

import pytest

SCRIPTS_DIR = os.path.join(os.path.dirname(__file__), '..', 'scripts')
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)


def _base_rules():
    return {
        'profit_harvest_pct': 0.50,
        'gamma_dte_threshold': 21,
        'earnings_days_threshold': 5,
        'dead_money_pl_pct_low': -0.10,
        'dead_money_pl_pct_high': 0.10,
        'dead_money_vrp_structural_threshold': 0.80,
        'theta_efficiency_low': 0.10,
        'hv_floor_percent': 5.0,
        'vrp_scalable_threshold': 1.50,
        'vrp_tactical_quality_warning_threshold': 0.50,
        'size_threat_pct': 0.05,
        'beta_weighted_symbol': 'SPY',
        'allow_proxy_stacking': True,
        'concentration_limit_pct': 0.05,
        'max_strategies_per_symbol': 3,
        'futures_delta_validation': {'enabled': False},
        'hedge_rules': {'enabled': False},
    }


@pytest.fixture
def base_rules():
    return _base_rules()


@pytest.fixture
def make_option_leg():
    def _make(**overrides):
        leg = {
            'Symbol': 'AAPL',
            'Type': 'Option',
            'Quantity': '-1',
            'Exp Date': '2099-12-31',
            'DTE': '30',
            'Strike Price': '100',
            'Call/Put': 'Call',
            'Underlying Last Price': '150',
            'P/L Open': '0',
            'Cost': '-100',
            'IV Rank': '0',
            'beta_delta': '-10',
            'Delta': '-0.10',
            'Theta': '1.0',
            'Gamma': '0.01',
            'beta_gamma': '',
            'Vega': '1.0',
            'Bid': '1.0',
            'Ask': '1.1',
            'Mark': '1.05',
            'Open Date': '2024-01-01',
        }
        leg.update(overrides)
        return leg
    return _make


@pytest.fixture
def make_triage_context(base_rules):
    def _make(**overrides):
        context = {
            'market_data': {
                'AAPL': {'vrp_structural': 1.0, 'vrp_tactical': 1.0, 'price': 150.0},
                'SPY': {'iv': 15.0, 'price': 400.0},
            },
            'rules': dict(base_rules),
            'market_config': {},
            'strategies': {},
            'traffic_jam_friction': 99.9,
            'portfolio_beta_delta': 0.0,
            'net_liquidity': 10000.0,
        }
        context.update(overrides)
        return context
    return _make
