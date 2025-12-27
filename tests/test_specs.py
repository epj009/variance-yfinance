"""
Unit tests for the Specification Pattern implementation.
"""

import numpy as np

from variance.models.market_specs import (
    CorrelationSpec,
    IVPercentileSpec,
    LiquiditySpec,
    LowVolTrapSpec,
    RetailEfficiencySpec,
    ScalableGateSpec,
    SectorExclusionSpec,
    VolatilityMomentumSpec,
    VolatilityTrapSpec,
    VrpStructuralSpec,
    VrpTacticalSpec,
)
from variance.models.specs import AndSpecification, NotSpecification, OrSpecification


def test_vrp_structural_spec():
    spec = VrpStructuralSpec(1.0)

    # Passing candidate
    assert spec.is_satisfied_by({"vrp_structural": 1.2}) is True
    # Failing candidate
    assert spec.is_satisfied_by({"vrp_structural": 0.8}) is False
    # Missing data
    assert spec.is_satisfied_by({}) is False


def test_low_vol_trap_spec():
    spec = LowVolTrapSpec(5.0)

    assert spec.is_satisfied_by({"hv252": 10.0}) is True
    assert spec.is_satisfied_by({"hv252": 2.0}) is False
    # Missing data should pass (conservative assumption)
    assert spec.is_satisfied_by({}) is True


def test_sector_exclusion_spec():
    spec = SectorExclusionSpec(["Technology", "Energy"])

    assert spec.is_satisfied_by({"sector": "Healthcare"}) is True
    assert spec.is_satisfied_by({"sector": "Technology"}) is False
    assert spec.is_satisfied_by({"sector": "energy"}) is False  # Case insensitive


def test_vrp_tactical_spec_no_mutation():
    spec = VrpTacticalSpec(5.0)
    metrics = {"iv": 20.0, "hv20": 10.0}

    assert spec.is_satisfied_by(metrics) is True
    assert "vrp_tactical" not in metrics


def test_vrp_tactical_spec_invalid_inputs():
    spec = VrpTacticalSpec(5.0)

    assert spec.is_satisfied_by({"iv": None, "hv20": 10.0}) is False
    assert spec.is_satisfied_by({"iv": 20.0, "hv20": None}) is False
    assert spec.is_satisfied_by({"iv": "bad", "hv20": 10.0}) is False
    assert spec.is_satisfied_by({"iv": 20.0, "hv20": 0.0}) is False


def test_liquidity_spec_tastytrade_rating():
    spec = LiquiditySpec(max_slippage=0.10, min_vol=100, min_tt_liquidity_rating=4)

    assert spec.is_satisfied_by({"symbol": "AAPL", "liquidity_rating": 5}) is True
    assert spec.is_satisfied_by({"symbol": "AAPL", "liquidity_rating": 3}) is False

    wide = {
        "symbol": "AAPL",
        "liquidity_rating": 5,
        "call_bid": 1.0,
        "call_ask": 2.0,
    }
    assert spec.is_satisfied_by(wide) is False


def test_liquidity_spec_fallbacks():
    spec = LiquiditySpec(max_slippage=0.10, min_vol=100)

    assert spec.is_satisfied_by({"symbol": "/ES"}) is True
    assert spec.is_satisfied_by({"symbol": "AAPL", "call_bid": 1.0, "call_ask": 1.05}) is True
    assert spec.is_satisfied_by({"symbol": "AAPL"}) is True
    assert spec.is_satisfied_by({"symbol": "AAPL", "atm_volume": 10}) is False


def test_correlation_spec_with_returns():
    portfolio = np.array([0.1, 0.2, 0.3, 0.4, 0.5])
    spec = CorrelationSpec(portfolio, max_correlation=0.9)

    assert spec.is_satisfied_by({"symbol": "AAPL", "returns": [0.1, 0.2, 0.3, 0.4, 0.5]}) is False
    assert spec.is_satisfied_by({"symbol": "AAPL", "returns": [0.5, 0.4, 0.3, 0.2, 0.1]}) is True


def test_correlation_spec_requires_returns_when_no_proxy():
    portfolio = np.array([0.1, 0.2, 0.3, 0.4, 0.5])
    spec = CorrelationSpec(portfolio, max_correlation=0.9)

    assert spec.is_satisfied_by({"symbol": "AAPL"}) is False


def test_correlation_spec_uses_proxy_for_futures(monkeypatch):
    portfolio = np.array([0.1, 0.2, 0.3, 0.4, 0.5])
    raw_data = {"SPY": {"returns": [0.1, 0.2, 0.3, 0.4, 0.5]}}
    spec = CorrelationSpec(portfolio, max_correlation=0.9, raw_data=raw_data)

    def fake_market_config():
        return {"FAMILY_MAP": {"equities": ["/ES", "SPY"]}}

    monkeypatch.setattr("variance.config_loader.load_market_config", fake_market_config)

    metrics = {"symbol": "/ES"}
    assert spec.is_satisfied_by(metrics) is False
    assert metrics.get("correlation_via_proxy") is True


def test_iv_percentile_spec():
    spec = IVPercentileSpec(min_percentile=30.0)

    assert spec.is_satisfied_by({"symbol": "/ES"}) is True
    assert spec.is_satisfied_by({"symbol": "AAPL", "iv_percentile": None}) is False
    assert spec.is_satisfied_by({"symbol": "AAPL", "iv_percentile": "bad"}) is False
    assert spec.is_satisfied_by({"symbol": "AAPL", "iv_percentile": 40.0}) is True


def test_volatility_trap_spec():
    spec = VolatilityTrapSpec(rank_threshold=15.0, vrp_rich_threshold=1.3)

    assert spec.is_satisfied_by({"vrp_structural": 1.4, "hv_rank": 10.0}) is False
    assert spec.is_satisfied_by({"vrp_structural": 1.4, "hv_rank": 20.0}) is True
    assert spec.is_satisfied_by({"vrp_structural": 1.0, "hv_rank": 5.0}) is True


def test_volatility_momentum_spec():
    spec = VolatilityMomentumSpec(min_momentum_ratio=0.85)

    assert spec.is_satisfied_by({"hv30": 15.0, "hv90": 25.0}) is False
    assert spec.is_satisfied_by({"hv30": 22.0, "hv90": 25.0}) is True
    assert spec.is_satisfied_by({"hv30": 15.0, "hv90": 0.0}) is True


def test_retail_efficiency_spec():
    spec = RetailEfficiencySpec(min_price=25.0, max_slippage=0.05)

    assert spec.is_satisfied_by({"symbol": "/CL"}) is True
    assert spec.is_satisfied_by({"symbol": "AAPL", "price": 10.0}) is False
    assert (
        spec.is_satisfied_by({"symbol": "AAPL", "price": 150.0, "call_bid": 1.0, "call_ask": 1.2})
        is False
    )
    assert spec.is_satisfied_by({"symbol": "AAPL", "price": 150.0}) is True


def test_scalable_gate_spec():
    spec = ScalableGateSpec(markup_threshold=0.2, divergence_threshold=1.5)

    assert spec.is_satisfied_by({"vrp_tactical_markup": 0.3, "vrp_structural": 1.0}) is True
    assert spec.is_satisfied_by({"vrp_tactical_markup": 0.1, "vrp_structural": 0.5}) is True
    assert spec.is_satisfied_by({"vrp_tactical_markup": 0.1, "vrp_structural": 2.0}) is False


def test_specification_and_operator():
    spec_a = VrpStructuralSpec(1.0)
    spec_b = LowVolTrapSpec(5.0)

    combined = spec_a & spec_b

    assert isinstance(combined, AndSpecification)
    assert combined.is_satisfied_by({"vrp_structural": 1.2, "hv252": 10.0}) is True
    assert combined.is_satisfied_by({"vrp_structural": 0.8, "hv252": 10.0}) is False
    assert combined.is_satisfied_by({"vrp_structural": 1.2, "hv252": 2.0}) is False


def test_specification_or_operator():
    spec_a = VrpStructuralSpec(1.5)
    spec_b = SectorExclusionSpec(["Technology"])

    combined = spec_a | spec_b

    assert isinstance(combined, OrSpecification)
    # Passes A
    assert combined.is_satisfied_by({"vrp_structural": 2.0, "sector": "Technology"}) is True
    # Passes B
    assert combined.is_satisfied_by({"vrp_structural": 1.0, "sector": "Healthcare"}) is True
    # Fails both
    assert combined.is_satisfied_by({"vrp_structural": 1.0, "sector": "Technology"}) is False


def test_specification_invert_operator():
    spec = VrpStructuralSpec(1.0)
    inverted = ~spec

    assert isinstance(inverted, NotSpecification)
    assert inverted.is_satisfied_by({"vrp_structural": 0.8}) is True
    assert inverted.is_satisfied_by({"vrp_structural": 1.2}) is False
