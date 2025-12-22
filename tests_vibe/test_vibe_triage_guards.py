import pytest

import triage_engine


def test_triage_uses_raw_delta_flag(make_option_leg, make_triage_context):
    leg = make_option_leg(beta_delta='', Delta='12.5')
    context = make_triage_context()

    result = triage_engine.triage_cluster([leg], context)

    assert 'unweighted Delta' in result['logic']


@pytest.mark.xfail(reason='EXPIRING should not be overridden by HARVEST when DTE=0.')
def test_expiring_action_has_priority(make_option_leg, make_triage_context):
    leg = make_option_leg(DTE='0', Cost='-100', **{'P/L Open': '50'})
    context = make_triage_context()

    result = triage_engine.triage_cluster([leg], context)

    assert result['action_code'] == 'EXPIRING'


def test_scalable_gate_handles_missing_beta_price(make_option_leg, make_triage_context):
    leg = make_option_leg(DTE='30', Cost='-100', **{'P/L Open': '0', 'Strike Price': '200'})
    market_data = {
        'AAPL': {'vrp_structural': 1.0, 'vrp_tactical': 3.0, 'price': 150.0},
    }
    context = make_triage_context(market_data=market_data)

    result = triage_engine.triage_cluster([leg], context)

    assert result['action_code'] == 'SCALABLE'
