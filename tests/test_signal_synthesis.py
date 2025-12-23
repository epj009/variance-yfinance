"""
Unit tests for Vol Screener Signal Synthesis logic.
Ensures that metrics (NVRP, VRP, Earnings) are correctly synthesized into Actionable Signals.
"""

import pytest

from variance import vol_screener


class TestSignalSynthesis:
    """Tests for _determine_signal_type logic."""

    @pytest.fixture
    def mock_rules(self):
        return {
            "vrp_structural_rich_threshold": 1.0,
            "vrp_structural_threshold": 0.85,
            "earnings_days_threshold": 5,
            "vrp_tactical_cheap_threshold": -0.10,
            "compression_coiled_threshold": 0.75,
            "compression_expanding_threshold": 1.0,
            "hv_rank_trap_threshold": 15.0,
        }

    def test_signal_event_dominates(self, mock_rules):
        """Earnings Event should override all other signals."""
        flags = {"is_earnings_soon": True, "is_cheap": True, "is_coiled": True}
        signal = vol_screener._determine_signal_type(flags, vrp_t_markup=-0.20, rules=mock_rules)
        assert signal == "EVENT"

    def test_signal_discount(self, mock_rules):
        """Cheap Tactical VRP triggers DISCOUNT."""
        flags = {"is_earnings_soon": False, "is_cheap": True, "is_coiled": False}
        signal = vol_screener._determine_signal_type(flags, vrp_t_markup=-0.15, rules=mock_rules)
        assert signal == "DISCOUNT"

    def test_signal_bound(self, mock_rules):
        """Coiled compression triggers BOUND."""
        flags = {"is_earnings_soon": False, "is_cheap": False, "is_coiled": True}
        signal = vol_screener._determine_signal_type(flags, vrp_t_markup=0.10, rules=mock_rules)
        assert signal == "BOUND"

    def test_signal_rich(self, mock_rules):
        """High Tactical Markup (>0.20) triggers RICH if not coiled."""
        flags = {"is_earnings_soon": False, "is_cheap": False, "is_coiled": False}
        # Markup > 0.20 is hardcoded in _determine_signal_type
        signal = vol_screener._determine_signal_type(flags, vrp_t_markup=0.25, rules=mock_rules)
        assert signal == "RICH"

    def test_signal_fair(self, mock_rules):
        """No flags triggered results in FAIR."""
        flags = {"is_earnings_soon": False, "is_cheap": False, "is_coiled": False}
        signal = vol_screener._determine_signal_type(flags, vrp_t_markup=0.10, rules=mock_rules)
        assert signal == "FAIR"


class TestVarianceScore:
    """Tests for _calculate_variance_score logic."""

    @pytest.fixture
    def mock_rules(self):
        return {"vrp_structural_rich_threshold": 1.0, "hv_rank_trap_threshold": 15.0}

    def test_score_calculation_balanced(self, mock_rules):
        """Score should average structural and tactical components (absolute distance)."""
        metrics = {
            "vrp_structural": 1.5,  # |1.5 - 1.0|*200 = 100 -> * 0.5 = 50
            "vrp_tactical": 1.5,  # |1.5 - 1.0|*200 = 100 -> * 0.5 = 50
            "hv_rank": 50,
        }
        score = vol_screener._calculate_variance_score(metrics, mock_rules)
        assert score == 100.0

    def test_score_cheap_vol_is_high(self, mock_rules):
        """Cheap vol (0.5 VRP) should now score high (100) instead of 0."""
        metrics = {
            "vrp_structural": 0.5,  # |0.5 - 1.0|*200 = 100
            "vrp_tactical": 0.5,  # |0.5 - 1.0|*200 = 100
            "hv_rank": 50,
        }
        score = vol_screener._calculate_variance_score(metrics, mock_rules)
        assert score == 100.0

    def test_score_penalty_trap(self, mock_rules):
        """Score should be penalized if it's a Short Vol Trap."""
        metrics = {
            "vrp_structural": 1.5,  # 100 pts -> 50 weighted
            "vrp_tactical": 1.5,  # 100 pts -> 50 weighted = 100 total
            "hv_rank": 10,  # Trap! (< 15)
        }
        # Trap penalty is 50%
        score = vol_screener._calculate_variance_score(metrics, mock_rules)
        assert score == 50.0

    def test_score_fallback_tactical(self, mock_rules):
        """If tactical missing, fallback to structural."""
        metrics = {
            "vrp_structural": 1.5,  # 100 pts
            "vrp_tactical": None,  # Missing
            "hv_rank": 50,
        }
        # Should use structural for both components (50 + 50)
        score = vol_screener._calculate_variance_score(metrics, mock_rules)
        assert score == 100.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
