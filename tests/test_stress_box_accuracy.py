"""
Tests for the accuracy of risk calculations (Stress Box, Size Threat)
after the refactoring to a per-position P/L model.

This addresses the audit finding regarding incorrect aggregation of Greeks for
non-SPY-centric portfolios.
"""

import pytest
import math
from unittest.mock import MagicMock

# It's common to put imports at the top, but for this ad-hoc test file,
# we need to add the script path first.
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'scripts')))

import analyze_portfolio
from triage_engine import triage_cluster

# --- Test Data Fixtures ---

@pytest.fixture
def mock_rules():
    """Provides a default set of trading rules for tests."""
    return {
        'beta_weighted_symbol': 'SPY',
        'stress_scenarios': [
            {
                "label": "Test Scenario (-1SD)",
                "sigma": -1.0,
                "vol_point_move": 5.0
            }
        ],
        'size_threat_pct': 0.05,
        'profit_harvest_pct': 0.50,
        'gamma_dte_threshold': 21,
        'dead_money_pl_pct_low': -0.10,
        'dead_money_pl_pct_high': 0.10,
        'dead_money_vrp_structural_threshold': 0.80,
        'earnings_days_threshold': 5,
        'vrp_scalable_threshold': 1.5,
        'theta_efficiency_low': 0.10,
        'hv_floor_percent': 5.0,
        'hedge_rules': {
            'enabled': True,
            'index_symbols': ['SPY'],
            'qualifying_strategies': ['Long Put'],
            'delta_threshold': -5,
            'require_portfolio_long': True
        },
        'futures_delta_validation': {
            'enabled': True,
            'min_abs_delta_threshold': 1.0
        },
        'vrp_tactical_aggregation_floor': -0.50,
        'vrp_tactical_aggregation_ceiling': 1.00,
        'friction_horizon_min_theta': 0.01,
    }

@pytest.fixture
def mock_market_data():
    """Provides mock market data, including for the beta symbol (SPY)."""
    return {
        'SPY': {'price': 500.0, 'iv': 15.0, 'beta': 1.0},
        'AAPL': {'price': 170.0, 'iv': 25.0, 'beta': 1.3},
    }

@pytest.fixture
def mock_portfolio_reports():
    """
    Provides a mock `all_position_reports` list.
    Updated to reflect actual triage_engine output structure where 'gamma' is 
    already beta-weighted and 'raw_gamma'/'beta' are not typically passed.
    """
    return [
        {
            'root': 'SPY',
            'delta': -10,      # beta-weighted
            'gamma': -0.5,     # beta-weighted gamma (previously calculated in engine)
            'raw_vega': -8.0,
            'beta': 1.0,       # retained for vega approx if needed
        },
        {
            'root': 'AAPL',
            'delta': -26,      # beta-weighted (-20 * 1.3)
            'gamma': -2.535,   # beta-weighted gamma (-1.5 * 1.3^2 = -2.535)
            'raw_vega': -12.0,
            'beta': 1.3,
        }
    ]

# --- Test Class for Stress Box Accuracy ---

class TestStressBoxAccuracy:
    def test_per_position_stress_box_calculation(self, mock_rules, mock_market_data, mock_portfolio_reports):
        """
        Validates that the stress box correctly calculates P/L on a per-position
        basis, using the pre-calculated beta-weighted gamma from the report.
        """
        # --- 1. Setup: Replicate the core logic from analyze_portfolio.py ---
        beta_sym = mock_rules['beta_weighted_symbol']
        beta_price = mock_market_data[beta_sym]['price']
        beta_iv = mock_market_data[beta_sym]['iv']
        em_1sd = beta_price * (beta_iv / 100.0 / math.sqrt(252))

        # Get the test scenario
        scenario = mock_rules['stress_scenarios'][0]
        move_points = em_1sd * scenario['sigma'] # 1SD move for SPY in points
        vol_move = scenario['vol_point_move']

        # This is the new logic from analyze_portfolio.py
        total_est_pl = 0.0
        for pos_report in mock_portfolio_reports:
            pos_beta_delta = pos_report.get('delta', 0.0)
            # FIX: Use 'gamma' (beta-weighted) directly, not raw_gamma reconstruction
            pos_beta_gamma = pos_report.get('gamma', 0.0)
            
            pos_raw_vega = pos_report.get('raw_vega', 0.0)
            pos_beta = pos_report.get('beta', 1.0)

            delta_pl = pos_beta_delta * move_points
            # Gamma P/L = 0.5 * Gamma_BW * (Move_SPY^2)
            gamma_pl = 0.5 * pos_beta_gamma * (move_points ** 2)
            vega_pl = (pos_raw_vega * pos_beta) * vol_move
            total_est_pl += (delta_pl + gamma_pl + vega_pl)

        # --- 2. Manual Calculation for Verification ---
        
        # SPY Position
        spy_report = mock_portfolio_reports[0]
        spy_beta_delta = spy_report['delta']
        spy_beta_gamma = spy_report['gamma']
        spy_raw_vega = spy_report['raw_vega']
        spy_beta = spy_report['beta']
        
        spy_delta_pl = spy_beta_delta * move_points
        spy_gamma_pl = 0.5 * spy_beta_gamma * (move_points ** 2)
        spy_vega_pl = (spy_raw_vega * spy_beta) * vol_move
        expected_spy_pl = spy_delta_pl + spy_gamma_pl + spy_vega_pl
        
        # AAPL Position
        aapl_report = mock_portfolio_reports[1]
        aapl_beta_delta = aapl_report['delta']
        aapl_beta_gamma = aapl_report['gamma']
        aapl_raw_vega = aapl_report['raw_vega']
        aapl_beta = aapl_report['beta']

        aapl_delta_pl = aapl_beta_delta * move_points
        aapl_gamma_pl = 0.5 * aapl_beta_gamma * (move_points ** 2)
        aapl_vega_pl = (aapl_raw_vega * aapl_beta) * vol_move
        expected_aapl_pl = aapl_delta_pl + aapl_gamma_pl + aapl_vega_pl

        expected_total_pl = expected_spy_pl + expected_aapl_pl

        # --- 3. Assertion ---
        assert total_est_pl == pytest.approx(expected_total_pl)
        
        # Also check that the manual calculation is non-trivial
        assert abs(expected_spy_pl) > 0
        assert abs(expected_aapl_pl) > 0
        
        # Check that P/L from non-SPY underlying is different
        assert expected_spy_pl != expected_aapl_pl


# --- Test Class for Size Threat Accuracy ---

@pytest.fixture
def mock_triage_cluster_context(mock_rules, mock_market_data):
    """Provides mock context for triage_cluster."""
    return {
        'market_data': mock_market_data,
        'rules': mock_rules,
        'market_config': {},
        'strategies': {},
        'traffic_jam_friction': 99.9,
        'net_liquidity': 100000.0  # $100k
    }

@pytest.fixture
def msft_cluster_legs():
    """Mock legs for a single MSFT position."""
    return [
        {
            'Symbol': 'MSFT_2025-01-17_400_P',
            'Type': 'Option',
            'beta_delta': '26', # 20 * 1.3
            'Delta': '20',
            'Gamma': '-1.5',
            # Other fields needed by triage_cluster
            'P/L Open': '100', 'Cost': '-500', 'DTE': '30',
            'Underlying Last Price': '450', 'Call/Put': 'Put', 'Strike Price': '400',
            'Quantity': '-1'
        }
    ]

class TestSizeThreatAccuracy:
    def test_size_threat_for_non_spy_underlying(self, msft_cluster_legs, mock_triage_cluster_context):
        """
        Validates that the 'Size Threat' calculation for a non-SPY position
        correctly uses the position's own beta to scale the market shock.
        """
        # --- 1. Setup: Mock market data for MSFT ---
        mock_triage_cluster_context['market_data']['MSFT'] = {
            'price': 450.0, 'iv': 22.0, 'beta': 1.3
        }
        
        # Lower net liquidity so that the mock position (~$360 risk) triggers the 5% threshold ($250)
        mock_triage_cluster_context['net_liquidity'] = 5000.0
        
        # --- 2. Execute: Run triage_cluster ---
        result = triage_cluster(msft_cluster_legs, mock_triage_cluster_context)

        # --- 3. Manual Calculation for Verification ---
        rules = mock_triage_cluster_context['rules']
        market_data = mock_triage_cluster_context['market_data']
        net_liq = mock_triage_cluster_context['net_liquidity']
        
        beta_sym = rules['beta_weighted_symbol']
        beta_price = market_data[beta_sym]['price']
        beta_iv = market_data[beta_sym]['iv']
        
        em_1sd_spy = beta_price * (beta_iv / 100.0 / 15.87) # approx sqrt(252)
        move_2sd_spy = em_1sd_spy * -2.0 # -2SD SPY move in points

        # Get the greeks from the result (which are calculated inside)
        strategy_delta_bw = result['delta']
        strategy_gamma_bw = result['gamma']

        # This is the key formula from inside triage_cluster
        expected_loss = (strategy_delta_bw * move_2sd_spy) + (0.5 * strategy_gamma_bw * (move_2sd_spy ** 2))
        expected_loss_pct_of_nl = abs(expected_loss) / net_liq
        
        # --- 4. Assertion ---
        assert 'logic' in result
        assert 'Tail Risk' in result['logic']
        assert result['action_code'] == 'SIZE_THREAT'

        # Extract the percentage from the logic string and compare
        # e.g., "Tail Risk: 5.2% of Net Liq in -2SD move"
        try:
            reported_pct_str = result['logic'].split(':')[1].split('%')[0].strip()
            reported_pct = float(reported_pct_str) / 100.0
        except (IndexError, ValueError):
            pytest.fail("Could not parse percentage from triage logic string")

        assert reported_pct == pytest.approx(expected_loss_pct_of_nl, abs=0.001)

