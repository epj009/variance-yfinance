from datetime import datetime, timedelta

from variance import triage_engine


def test_validate_futures_delta_low_delta_flags(mock_market_config):
    rules = {"futures_delta_validation": {"enabled": True, "min_abs_delta_threshold": 2.0}}
    result = triage_engine.validate_futures_delta("/ES", 1.0, mock_market_config, rules)

    assert result["is_futures"] is True
    assert result["potential_issue"] is True
    assert result["multiplier"] == 50
    assert "Low Beta Delta" in result["message"]


def test_validate_futures_delta_disabled(mock_market_config):
    rules = {"futures_delta_validation": {"enabled": False}}
    result = triage_engine.validate_futures_delta("/ES", 0.2, mock_market_config, rules)

    assert result["is_futures"] is True
    assert result["potential_issue"] is False
    assert result["multiplier"] is None


def test_beta_weight_gamma_prefers_beta_gamma():
    leg = {"Gamma": "0.05", "beta_gamma": "0.12"}
    assert triage_engine._beta_weight_gamma(leg) == 0.12


def test_beta_weight_gamma_scales_from_beta_delta():
    leg = {"Gamma": "0.5", "beta_gamma": "", "beta_delta": "20", "Delta": "10"}
    assert triage_engine._beta_weight_gamma(leg) == 2.0


def test_calculate_days_held_handles_formats():
    today = datetime.now().date()
    older = today - timedelta(days=7)
    newer = today - timedelta(days=3)

    legs = [
        {"Open Date": older.isoformat()},
        {"Open Date": newer.strftime("%b %d %Y")},
    ]

    assert triage_engine.calculate_days_held(legs) == 3


def test_calculate_cluster_metrics_uses_raw_delta_and_warns_futures(mock_market_config):
    rules = {
        "futures_delta_validation": {"enabled": True, "min_abs_delta_threshold": 1.0},
        "hedge_rules": {"enabled": False},
    }
    context = {
        "market_data": {"/ES": {"price": 4500.0, "vrp_structural": 1.0}},
        "market_config": mock_market_config,
        "rules": rules,
    }
    legs = [
        {
            "Symbol": "/ESZ5",
            "Type": "Option",
            "Call/Put": "Put",
            "Quantity": "-1",
            "Strike Price": "4500",
            "Exp Date": "2025-01-17",
            "DTE": "10",
            "Cost": "-100",
            "P/L Open": "10",
            "Delta": "0.2",
            "beta_delta": "",
            "Theta": "-1",
            "Gamma": "0.05",
            "Bid": "1.0",
            "Ask": "1.1",
            "Underlying Last Price": "4500",
        }
    ]

    metrics = triage_engine.calculate_cluster_metrics(legs, context)

    assert metrics["uses_raw_delta"] is True
    assert metrics["futures_delta_warnings"]


def test_get_position_aware_opportunities_excludes_concentrated(monkeypatch):
    import numpy as np

    from variance import vol_screener
    from variance.models import correlation as correlation_module

    captured = {}

    def fake_screen_volatility(config, **_kwargs):
        captured["config"] = config
        return {"candidates": [], "summary": {"ok": True}}

    monkeypatch.setattr(vol_screener, "screen_volatility", fake_screen_volatility)
    monkeypatch.setattr(
        correlation_module.CorrelationEngine,
        "get_portfolio_proxy_returns",
        lambda _returns: np.array([0.01]),
    )

    positions = [
        {"Symbol": "AAPL", "Cost": "-100"},
        {"Symbol": "MSFT", "Cost": "-10"},
    ]
    clusters = [
        [{"Symbol": "AAPL"}],
        [{"Symbol": "AAPL"}],
        [{"Symbol": "MSFT"}],
    ]
    rules = {
        "concentration_limit_pct": 0.05,
        "max_strategies_per_symbol": 2,
        "allow_proxy_stacking": True,
        "vrp_structural_threshold": 0.85,
        "min_variance_score": 10.0,
        "min_iv_percentile": 0.0,
    }
    market_data = {
        "AAPL": {"returns": [0.01, 0.02]},
        "MSFT": {"returns": [0.0, 0.01]},
    }

    result = triage_engine.get_position_aware_opportunities(
        positions=positions,
        clusters=clusters,
        net_liquidity=1000.0,
        rules=rules,
        market_data=market_data,
    )

    assert set(result["meta"]["excluded_symbols"]) == {"AAPL"}
    config = captured["config"]
    assert config.exclude_symbols == ["AAPL"]
    assert set(config.held_symbols) == {"AAPL", "MSFT"}
