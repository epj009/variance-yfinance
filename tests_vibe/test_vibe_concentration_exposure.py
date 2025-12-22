import triage_engine
import vol_screener


def test_concentration_parses_broker_currency(monkeypatch, make_option_leg, base_rules):
    captured = {}

    def fake_screen(config):
        captured['config'] = config
        return {'candidates': [], 'summary': {}}

    monkeypatch.setattr(vol_screener, 'screen_volatility', fake_screen)

    positions = [
        {
            **make_option_leg(Symbol='AAPL', Cost='$1,200').copy(),
        }
    ]
    clusters = [[positions[0]]]

    rules = dict(base_rules)
    rules['concentration_limit_pct'] = 0.05
    rules['max_strategies_per_symbol'] = 3
    rules['allow_proxy_stacking'] = True

    triage_engine.get_position_aware_opportunities(
        positions=positions,
        clusters=clusters,
        net_liquidity=10000.0,
        rules=rules,
    )

    assert 'AAPL' in captured['config'].exclude_symbols
