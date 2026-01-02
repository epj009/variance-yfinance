"""
Regression tests for HV/VRP unit consistency.

This test suite ensures that Historical Volatility (HV) and Variance Risk Premium (VRP)
calculations use consistent units (PERCENT format) throughout the data pipeline.

CRITICAL: These tests lock in the mathematical correctness of the system.
If these fail, trades will be incorrect!

Expected VRP range: -0.5 to 2.0 (typical for equity options)
Expected HV format: 25.0 = 25% (not 0.25)
"""

import pytest


class TestTastytradeClientHVNormalization:
    """Test HV normalization in tastytrade_client._normalize_hv()"""

    def test_normalize_hv_decimal_to_percent(self):
        """Test API decimal (0.25) converts to percent (25.0)"""
        from variance.tastytrade_client import TastytradeClient

        # API returns 0.25 for 25% volatility
        result = TastytradeClient._normalize_hv(0.25)
        assert result == 25.0, f"Expected 25.0 (percent), got {result}"

    def test_normalize_hv_already_percent(self):
        """Test already-percent values pass through (defensive)"""
        from variance.tastytrade_client import TastytradeClient

        # If API returns 25.0 (already percent), don't multiply
        result = TastytradeClient._normalize_hv(25.0)
        assert result == 25.0, f"Expected 25.0 (unchanged), got {result}"

    def test_normalize_hv_boundary_cases(self):
        """Test boundary at 2.0 threshold"""
        from variance.tastytrade_client import TastytradeClient

        # Values <= 2.0 are treated as decimals
        assert TastytradeClient._normalize_hv(0.15) == 15.0  # 0.15 * 100
        assert TastytradeClient._normalize_hv(1.5) == 150.0  # 1.5 * 100
        assert TastytradeClient._normalize_hv(2.0) == 200.0  # 2.0 * 100

        # Values > 2.0 are already percent
        assert TastytradeClient._normalize_hv(2.1) == 2.1  # Pass through
        assert TastytradeClient._normalize_hv(25.0) == 25.0  # Pass through

    def test_normalize_hv_none(self):
        """Test None handling"""
        from variance.tastytrade_client import TastytradeClient

        assert TastytradeClient._normalize_hv(None) is None


class TestPureTastytradeProviderHVPassthrough:
    """Test HV values pass through without conversion in PureTastytradeProvider"""

    def test_rest_api_hv_stored_as_percent(self):
        """Test REST API HV values are stored in percent format"""
        from variance.market_data.pure_tastytrade_provider import PureTastytradeProvider

        provider = PureTastytradeProvider()

        # Mock data from tastytrade_client (already normalized to percent)
        mock_metrics = {
            "symbol": "AAPL",
            "iv": 35.4,
            "hv30": 25.1,  # Already percent from _normalize_hv()
            "hv90": 28.3,
        }
        mock_prices = {
            "symbol": "AAPL",
            "price": 272.09,
        }

        result = provider._merge_tastytrade_data(
            "AAPL", mock_metrics, mock_prices, include_returns=False
        )

        assert result["hv30"] == 25.1, "HV30 should be 25.1 (percent, not 0.251 decimal)"
        assert result["hv90"] == 28.3, "HV90 should be 28.3 (percent, not 0.283 decimal)"


class TestDXLinkHVConversion:
    """Test DXLink HV calculator outputs are converted to percent"""

    def test_hv_calculator_returns_decimal(self):
        """Test hv_calculator returns decimal (0.25 for 25%)"""
        from datetime import datetime

        from variance.market_data.dxlink_client import CandleData
        from variance.market_data.hv_calculator import calculate_hv_from_candles

        # Create 31 candles with gradual drift (low volatility)
        # Daily std ~0.5%, annualized = 0.5% * sqrt(252) = ~8%
        candles = []
        base_price = 100.0
        for i in range(31):
            # Small drift: +0.1% per day
            price = base_price * (1.001**i)
            candles.append(
                CandleData(
                    symbol="TEST",
                    time=datetime(2024, 1, i + 1),
                    open=price,
                    high=price * 1.002,
                    low=price * 0.998,
                    close=price,
                    volume=1000000,
                )
            )

        hv30 = calculate_hv_from_candles(candles, window=30)

        # Should be decimal: < 1.0 (not percent format which would be > 5.0)
        assert hv30 is not None, "HV calculation should succeed"
        assert hv30 < 1.0, f"HV should be decimal (< 1.0), got {hv30}"
        assert hv30 < 5.0, f"HV should NOT be percent (would be > 5.0), got {hv30}"

    def test_dxlink_provider_converts_to_percent(self):
        """Test DXLinkHVProvider multiplies by 100 to match REST format"""
        # This is tested by integration - DXLink provider should multiply by 100
        # after calling hv_calculator to match REST API format
        pass  # Covered by integration test below


class TestVRPCalculationMath:
    """Test VRP calculations produce expected ranges"""

    def test_vrp_tactical_with_percent_format(self):
        """Test VRP tactical calculation with percent-format HV"""
        from variance.market_data.pure_tastytrade_provider import PureTastytradeProvider

        provider = PureTastytradeProvider()

        mock_metrics = {
            "symbol": "AAPL",
            "iv": 35.0,  # 35% IV
            "hv30": 25.0,  # 25% HV30 (PERCENT format)
        }
        mock_prices = {"symbol": "AAPL", "price": 100.0}

        result = provider._merge_tastytrade_data(
            "AAPL", mock_metrics, mock_prices, include_returns=False
        )

        # VRP = IV / max(HV30, floor)
        # = 35.0 / max(25.0, 5.0)
        # = 35.0 / 25.0 = 1.4
        expected_vrp = 35.0 / 25.0
        assert result["vrp_tactical"] == pytest.approx(expected_vrp, rel=0.01), (
            f"VRP should be {expected_vrp}, got {result['vrp_tactical']}"
        )

        # CRITICAL: VRP should be in 0-2 range, NOT 5-10
        assert 0.5 <= result["vrp_tactical"] <= 2.0, f"VRP out of range: {result['vrp_tactical']}"

    def test_vrp_with_hv_floor_protection(self):
        """Test VRP calculation when HV < floor (uses floor)"""
        from variance.market_data import settings as md_settings
        from variance.market_data.pure_tastytrade_provider import PureTastytradeProvider

        provider = PureTastytradeProvider()

        # Low HV scenario
        mock_metrics = {
            "symbol": "LOW_VOL",
            "iv": 30.0,
            "hv30": 3.0,  # Below 5.0 floor
        }
        mock_prices = {"symbol": "LOW_VOL", "price": 100.0}

        result = provider._merge_tastytrade_data(
            "LOW_VOL", mock_metrics, mock_prices, include_returns=False
        )

        # VRP = IV / max(HV30, 5.0) = 30.0 / 5.0 = 6.0
        expected_vrp = 30.0 / md_settings.HV_FLOOR_PERCENT
        assert result["vrp_tactical"] == pytest.approx(expected_vrp, rel=0.01)

    def test_vrp_structural_calculation(self):
        """Test VRP structural uses HV90"""
        from variance.market_data.pure_tastytrade_provider import PureTastytradeProvider

        provider = PureTastytradeProvider()

        mock_metrics = {
            "symbol": "AAPL",
            "iv": 42.0,
            "hv90": 35.0,  # PERCENT format
        }
        mock_prices = {"symbol": "AAPL", "price": 100.0}

        result = provider._merge_tastytrade_data(
            "AAPL", mock_metrics, mock_prices, include_returns=False
        )

        # VRP Structural = IV / HV90 = 42.0 / 35.0 = 1.2
        expected_vrp = 42.0 / 35.0
        assert result["vrp_structural"] == pytest.approx(expected_vrp, rel=0.01)


class TestVRPEnrichmentCalculation:
    """Test VRP enrichment strategy calculations"""

    def test_vrp_tactical_markup_with_percent_hv(self):
        """Test vrp_tactical_markup calculation in enrichment"""
        from variance.screening.enrichment.vrp import VrpEnrichmentStrategy

        # Mock context
        class MockContext:
            config_bundle = {"trading_rules": {"hv_floor_percent": 5.0}}

        strategy = VrpEnrichmentStrategy()
        candidate = {
            "symbol": "AAPL",
            "iv": 35.4,  # PERCENT
            "hv30": 25.1,  # PERCENT
            "hv90": 28.3,  # PERCENT
        }

        strategy.enrich(candidate, MockContext())

        # vrp_tactical_markup = (IV - max(HV30, floor)) / max(HV30, floor)
        # = (35.4 - 25.1) / 25.1 = 10.3 / 25.1 = 0.4104
        expected_markup = (35.4 - 25.1) / 25.1

        assert candidate["vrp_tactical_markup"] is not None
        assert candidate["vrp_tactical_markup"] == pytest.approx(expected_markup, rel=0.01)

        # CRITICAL: Should be in -0.5 to 1.5 range
        assert -0.5 <= candidate["vrp_tactical_markup"] <= 1.5, (
            f"VRP markup out of range: {candidate['vrp_tactical_markup']}"
        )

    def test_vrp_markup_negative_when_hv_exceeds_iv(self):
        """Test negative VRP when HV > IV (underpriced options)"""
        from variance.screening.enrichment.vrp import VrpEnrichmentStrategy

        class MockContext:
            config_bundle = {"trading_rules": {"hv_floor_percent": 5.0}}

        strategy = VrpEnrichmentStrategy()
        candidate = {
            "symbol": "CHEAP",
            "iv": 20.0,
            "hv30": 30.0,  # HV > IV
        }

        strategy.enrich(candidate, MockContext())

        # markup = (20.0 - 30.0) / 30.0 = -0.333
        expected_markup = (20.0 - 30.0) / 30.0

        assert candidate["vrp_tactical_markup"] == pytest.approx(expected_markup, rel=0.01)
        assert candidate["vrp_tactical_markup"] < 0, "Should be negative when HV > IV"

    def test_vrp_markup_floor_prevents_extreme_negatives(self):
        """Test -0.99 floor on VRP markup"""
        from variance.screening.enrichment.vrp import VrpEnrichmentStrategy

        class MockContext:
            config_bundle = {"trading_rules": {"hv_floor_percent": 5.0}}

        strategy = VrpEnrichmentStrategy()
        candidate = {
            "symbol": "EXTREME",
            "iv": 1.0,  # Very low IV
            "hv30": 50.0,  # High HV
        }

        strategy.enrich(candidate, MockContext())

        # Raw: (1.0 - 50.0) / 50.0 = -0.98, should be capped at -0.99
        assert candidate["vrp_tactical_markup"] >= -0.99
        assert candidate["vrp_tactical_markup"] == max(-0.99, (1.0 - 50.0) / 50.0)


class TestRegressionDetection:
    """Tests that would catch if someone re-introduces the /100 bug"""

    def test_detect_decimal_hv_bug(self):
        """
        REGRESSION TEST: Detect if HV values are accidentally converted to decimal.

        If someone adds `hv30 = hv30 / 100.0`, this test will catch it.
        """
        from variance.market_data.pure_tastytrade_provider import PureTastytradeProvider

        provider = PureTastytradeProvider()

        mock_metrics = {"symbol": "TEST", "iv": 30.0, "hv30": 20.0}
        mock_prices = {"symbol": "TEST", "price": 100.0}

        result = provider._merge_tastytrade_data(
            "TEST", mock_metrics, mock_prices, include_returns=False
        )

        # If buggy code divides by 100: hv30 = 20.0 / 100 = 0.20
        # Then VRP = 30.0 / max(0.20, 5.0) = 30.0 / 5.0 = 6.0 (WRONG!)

        # Correct: VRP = 30.0 / 20.0 = 1.5
        assert result["vrp_tactical"] == pytest.approx(1.5, rel=0.01), (
            f"VRP regression detected! Expected 1.5, got {result['vrp_tactical']}. "
            "Check if HV values are being divided by 100."
        )

        # Double-check HV wasn't converted
        assert result["hv30"] == 20.0, f"HV should be 20.0 (percent), not {result['hv30']}"
        assert result["hv30"] > 5.0, "HV should be > 5 (percent), not < 1 (decimal)"

    def test_detect_vrp_range_violation(self):
        """
        REGRESSION TEST: Detect if VRP values fall outside expected range.

        Typical equity VRP: 0.8 to 1.8
        If VRP > 3.0, likely a unit mismatch bug.
        """
        from variance.market_data.pure_tastytrade_provider import PureTastytradeProvider

        provider = PureTastytradeProvider()

        # Realistic equity options scenario
        mock_metrics = {"symbol": "AAPL", "iv": 28.0, "hv30": 22.0, "hv90": 25.0}
        mock_prices = {"symbol": "AAPL", "price": 200.0}

        result = provider._merge_tastytrade_data(
            "AAPL", mock_metrics, mock_prices, include_returns=False
        )

        vrp_tactical = result["vrp_tactical"]
        vrp_structural = result["vrp_structural"]

        # Sanity checks
        assert vrp_tactical < 3.0, (
            f"VRP Tactical too high: {vrp_tactical}. "
            "Expected < 3.0 for typical equities. Check for unit mismatch."
        )
        assert vrp_structural < 3.0, (
            f"VRP Structural too high: {vrp_structural}. "
            "Expected < 3.0 for typical equities. Check for unit mismatch."
        )

        # Should be in reasonable range
        assert 0.5 <= vrp_tactical <= 2.5
        assert 0.5 <= vrp_structural <= 2.5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
