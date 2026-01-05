"""
Unit tests for Vol Screener Signal Synthesis logic.
Ensures that metrics (NVRP, VRP, Earnings) are correctly synthesized into Actionable Signals.
"""

import pytest

from variance import vol_screener
from variance.signals.classifier import determine_signal_type


class TestSignalSynthesis:
    """Tests for _determine_signal_type logic."""

    @pytest.fixture
    def mock_rules(self):
        return {
            "vrp_structural_rich_threshold": 1.0,
            "vrp_structural_threshold": 0.85,
            "earnings_days_threshold": 5,
            "vrp_tactical_cheap_threshold": -0.10,
            "vtr_coiled_threshold": 0.75,
        }

    def test_signal_event_dominates(self, mock_rules):
        """Earnings Event should override all other signals."""
        flags = {"is_earnings_soon": True, "is_cheap": True, "is_rich": False}
        signal = determine_signal_type(
            flags,
            vrp_t_markup=-0.20,
            rules=mock_rules,
            vol_trend_ratio=0.52,
            hv20=15.0,
            hv60=20.0,
        )
        assert signal == "EVENT"

    def test_signal_discount(self, mock_rules):
        """Cheap Tactical VRP triggers DISCOUNT."""
        flags = {"is_earnings_soon": False, "is_cheap": True, "is_rich": False}
        signal = determine_signal_type(
            flags,
            vrp_t_markup=-0.15,
            rules=mock_rules,
            vol_trend_ratio=0.95,
            hv20=20.0,
            hv60=20.0,
        )
        assert signal == "DISCOUNT"

    def test_signal_coiled_severe(self, mock_rules):
        """Severe compression (< 0.60) should return COILED-SEVERE."""
        flags = {"is_earnings_soon": False, "is_cheap": False, "is_rich": False}
        signal = determine_signal_type(
            flags,
            vrp_t_markup=0.10,
            rules=mock_rules,
            vol_trend_ratio=0.52,
            hv20=15.0,
            hv60=20.0,
        )
        assert signal == "COILED-SEVERE"

    def test_signal_coiled_mild(self, mock_rules):
        """Mild compression (0.60-0.75) should return COILED-MILD."""
        flags = {"is_earnings_soon": False, "is_cheap": False, "is_rich": False}
        signal = determine_signal_type(
            flags,
            vrp_t_markup=0.10,
            rules=mock_rules,
            vol_trend_ratio=0.72,
            hv20=18.0,
            hv60=22.0,
        )
        assert signal == "COILED-MILD"

    def test_signal_expanding_severe(self, mock_rules):
        """Expanding volatility (> 1.30) should return EXPANDING-SEVERE."""
        flags = {"is_earnings_soon": False, "is_cheap": False, "is_rich": False}
        signal = determine_signal_type(
            flags,
            vrp_t_markup=0.10,
            rules=mock_rules,
            vol_trend_ratio=1.45,
        )
        assert signal == "EXPANDING-SEVERE"

    def test_signal_rich(self, mock_rules):
        """High Tactical Markup (>0.20) triggers RICH if not coiled."""
        flags = {"is_earnings_soon": False, "is_cheap": False, "is_rich": False}
        # Markup > 0.20 is hardcoded in determine_signal_type
        signal = determine_signal_type(
            flags,
            vrp_t_markup=0.25,
            rules=mock_rules,
            vol_trend_ratio=0.95,
            hv20=20.0,
            hv60=20.0,
        )
        assert signal == "RICH"

    def test_signal_fair(self, mock_rules):
        """No flags triggered results in FAIR."""
        flags = {"is_earnings_soon": False, "is_cheap": False, "is_rich": False}
        signal = determine_signal_type(
            flags,
            vrp_t_markup=0.10,
            rules=mock_rules,
            vol_trend_ratio=0.95,
            hv20=20.0,
            hv60=20.0,
        )
        assert signal == "FAIR"

    def test_signal_composite_check(self, mock_rules):
        """Long-term compressed but medium-term normal should not coil."""
        flags = {"is_earnings_soon": False, "is_cheap": False, "is_rich": False}
        signal = determine_signal_type(
            flags,
            vrp_t_markup=0.10,
            rules=mock_rules,
            vol_trend_ratio=0.70,
            hv20=25.0,
            hv60=23.0,
        )
        assert signal == "FAIR"


class TestVarianceScore:
    """Tests for _calculate_variance_score logic."""

    @pytest.fixture
    def mock_rules(self):
        return {
            "vrp_structural_rich_threshold": 1.0,
            "variance_score_dislocation_multiplier": 200,
            "variance_score_weights": {
                "structural_vrp": 0.5,
                "tactical_vrp": 0.5,
                "volatility_momentum": 0.0,
                "iv_percentile": 0.0,
                "yield": 0.0,
                "retail_efficiency": 0.0,
                "liquidity": 0.0,
            },
        }

    def test_score_calculation_balanced(self, mock_rules):
        """Score should average structural and tactical components (absolute distance)."""
        metrics = {
            "vrp_structural": 1.5,  # |1.5 - 1.0|*200 = 100 -> * 0.5 = 50
            "vrp_tactical": 1.5,  # |1.5 - 1.0|*200 = 100 -> * 0.5 = 50
        }
        score = vol_screener._calculate_variance_score(metrics, mock_rules)
        assert score == 100.0

    def test_score_cheap_vol_is_high(self, mock_rules):
        """Cheap vol (0.5 VRP) should now score high (100) instead of 0."""
        metrics = {
            "vrp_structural": 0.5,  # |0.5 - 1.0|*200 = 100
            "vrp_tactical": 0.5,  # |0.5 - 1.0|*200 = 100
        }
        score = vol_screener._calculate_variance_score(metrics, mock_rules)
        assert score == 100.0

    def test_score_fallback_tactical(self, mock_rules):
        """If tactical missing, fallback to structural."""
        metrics = {
            "vrp_structural": 1.5,  # 100 pts
            "vrp_tactical": None,  # Missing
        }
        # Should use structural for both components (50 + 50)
        score = vol_screener._calculate_variance_score(metrics, mock_rules)
        assert score == 100.0

    def test_score_momentum_component(self, mock_rules):
        rules = dict(mock_rules)
        rules["variance_score_weights"] = {
            "structural_vrp": 0.0,
            "tactical_vrp": 0.0,
            "volatility_momentum": 1.0,
            "iv_percentile": 0.0,
            "yield": 0.0,
            "retail_efficiency": 0.0,
            "liquidity": 0.0,
        }
        rules["volatility_momentum_min_ratio"] = 0.85
        rules["variance_score_momentum_ceiling"] = 1.20
        metrics = {"hv30": 12.0, "hv90": 10.0}
        score = vol_screener._calculate_variance_score(metrics, rules)
        assert score == 100.0

    def test_score_iv_percentile_component(self, mock_rules):
        rules = dict(mock_rules)
        rules["variance_score_weights"] = {
            "structural_vrp": 0.0,
            "tactical_vrp": 0.0,
            "volatility_momentum": 0.0,
            "iv_percentile": 1.0,
            "yield": 0.0,
            "retail_efficiency": 0.0,
            "liquidity": 0.0,
        }
        rules["min_iv_percentile"] = 50.0
        metrics = {"iv_percentile": 75.0}
        score = vol_screener._calculate_variance_score(metrics, rules)
        assert score == 50.0

    def test_score_yield_component(self, mock_rules):
        rules = dict(mock_rules)
        rules["variance_score_weights"] = {
            "structural_vrp": 0.0,
            "tactical_vrp": 0.0,
            "volatility_momentum": 0.0,
            "iv_percentile": 0.0,
            "yield": 1.0,
            "retail_efficiency": 0.0,
            "liquidity": 0.0,
        }
        rules["min_yield_percent"] = 3.0
        rules["variance_score_yield_ceiling"] = 15.0
        metrics = {"price": 100.0, "atm_bid": 3.0, "atm_ask": 3.0}
        score = vol_screener._calculate_variance_score(metrics, rules)
        assert score == pytest.approx(58.3)

    def test_score_retail_efficiency_component(self, mock_rules):
        rules = dict(mock_rules)
        rules["variance_score_weights"] = {
            "structural_vrp": 0.0,
            "tactical_vrp": 0.0,
            "volatility_momentum": 0.0,
            "iv_percentile": 0.0,
            "yield": 0.0,
            "retail_efficiency": 1.0,
            "liquidity": 0.0,
        }
        rules["retail_min_price"] = 25.0
        rules["retail_max_slippage"] = 0.05
        rules["variance_score_retail_price_ceiling"] = 100.0
        metrics = {"price": 50.0, "call_bid": 1.0, "call_ask": 1.05}
        score = vol_screener._calculate_variance_score(metrics, rules)
        assert score == pytest.approx(17.9)

    def test_score_liquidity_component(self, mock_rules):
        rules = dict(mock_rules)
        rules["variance_score_weights"] = {
            "structural_vrp": 0.0,
            "tactical_vrp": 0.0,
            "volatility_momentum": 0.0,
            "iv_percentile": 0.0,
            "yield": 0.0,
            "retail_efficiency": 0.0,
            "liquidity": 1.0,
        }
        rules["min_tt_liquidity_rating"] = 4
        metrics = {"liquidity_rating": 5}
        score = vol_screener._calculate_variance_score(metrics, rules)
        assert score == 100.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
