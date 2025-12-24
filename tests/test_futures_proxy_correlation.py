"""
Tests for Futures Proxy-Based Correlation (RFC 013/020 Implementation)

Validates that futures symbols use ETF proxies from FAMILY_MAP for correlation
calculation when direct returns data is unavailable.
"""

import numpy as np

from variance.models.market_specs import CorrelationSpec
from variance.screening.steps.filter import apply_specifications
from variance.vol_screener import ScreenerConfig


class TestFuturesProxyCorrelationUnit:
    """Unit tests for CorrelationSpec proxy lookup logic."""

    def test_futures_uses_etf_proxy_from_family_map(self):
        """Test that /ES uses SPY returns for correlation when /ES has no returns."""
        portfolio_returns = np.array([0.01, -0.02, 0.015, -0.01, 0.02])

        # Raw data: /ES has no returns, SPY has returns
        raw_data = {
            "/ES": {
                "symbol": "/ES",
                "returns": [],  # Futures often have no returns
                "vrp_structural": 0.85,
            },
            "SPY": {
                "symbol": "SPY",
                "returns": [0.012, -0.018, 0.014, -0.009, 0.021],  # Similar to portfolio
                "vrp_structural": 0.90,
            },
        }

        spec = CorrelationSpec(portfolio_returns, max_correlation=0.70, raw_data=raw_data)

        # Create candidate metrics for /ES
        es_metrics = {
            "symbol": "/ES",
            "returns": [],  # No direct returns
            "vrp_structural": 0.85,
        }

        # Should use SPY proxy and calculate correlation
        result = spec.is_satisfied_by(es_metrics)

        # Assertions
        assert "correlation_via_proxy" in es_metrics
        assert es_metrics["correlation_via_proxy"] is True
        assert "portfolio_rho" in es_metrics
        # High correlation with SPY-like returns should fail 0.70 threshold
        assert result is False  # Rejected due to high correlation

    def test_futures_with_direct_returns_doesnt_use_proxy(self):
        """Test that futures with direct returns don't use proxy."""
        portfolio_returns = np.array([0.01, -0.02, 0.015, -0.01, 0.02])

        raw_data = {
            "/ES": {
                "symbol": "/ES",
                "returns": [0.005, -0.003, 0.002, -0.001, 0.004],  # Has returns
                "vrp_structural": 0.85,
            },
            "SPY": {
                "symbol": "SPY",
                "returns": [0.012, -0.018, 0.014, -0.009, 0.021],
                "vrp_structural": 0.90,
            },
        }

        spec = CorrelationSpec(portfolio_returns, max_correlation=0.70, raw_data=raw_data)

        es_metrics = {
            "symbol": "/ES",
            "returns": [0.005, -0.003, 0.002, -0.001, 0.004],
            "vrp_structural": 0.85,
        }
        spec.is_satisfied_by(es_metrics)

        # Should NOT use proxy since it has returns
        assert "correlation_via_proxy" not in es_metrics
        assert "portfolio_rho" in es_metrics

    def test_futures_low_correlation_via_proxy_passes(self):
        """Test that /GC uses GLD proxy for correlation calculation."""
        portfolio_returns = np.array([0.01, -0.02, 0.015, -0.01, 0.02])

        # Create uncorrelated GLD returns using orthogonal sine wave
        gld_returns = [0.005 * np.sin(i * 0.7) for i in range(5)]

        raw_data = {
            "/GC": {
                "symbol": "/GC",
                "returns": [],
                "vrp_structural": 1.30,
            },
            "GLD": {
                "symbol": "GLD",
                "returns": gld_returns,
                "vrp_structural": 1.25,
            },
        }

        spec = CorrelationSpec(portfolio_returns, max_correlation=0.95, raw_data=raw_data)

        gc_metrics = {
            "symbol": "/GC",
            "returns": [],
            "vrp_structural": 1.30,
        }

        result = spec.is_satisfied_by(gc_metrics)

        # Should use GLD proxy for correlation calculation
        assert gc_metrics["correlation_via_proxy"] is True
        assert "portfolio_rho" in gc_metrics
        # With higher threshold, should pass
        assert result is True

    def test_futures_no_proxy_available_rejected(self):
        """Test that futures without proxy in FAMILY_MAP are rejected."""
        portfolio_returns = np.array([0.01, -0.02, 0.015, -0.01, 0.02])

        raw_data = {
            "/XYZ": {  # Hypothetical futures not in FAMILY_MAP
                "symbol": "/XYZ",
                "returns": [],
                "vrp_structural": 1.10,
            },
            # No proxy available in raw_data
        }

        spec = CorrelationSpec(portfolio_returns, max_correlation=0.70, raw_data=raw_data)

        xyz_metrics = {
            "symbol": "/XYZ",
            "returns": [],
            "vrp_structural": 1.10,
        }

        result = spec.is_satisfied_by(xyz_metrics)

        # Should reject due to no proxy available
        assert "correlation_via_proxy" not in xyz_metrics
        assert result is False

    def test_equity_symbol_not_using_proxy(self):
        """Test that equity symbols don't attempt proxy lookup."""
        portfolio_returns = np.array([0.01, -0.02, 0.015, -0.01, 0.02])

        raw_data = {
            "AAPL": {
                "symbol": "AAPL",
                "returns": [0.008, -0.015, 0.012, -0.008, 0.018],
                "vrp_structural": 0.95,
            },
        }

        spec = CorrelationSpec(portfolio_returns, max_correlation=0.70, raw_data=raw_data)

        aapl_metrics = {
            "symbol": "AAPL",
            "returns": [0.008, -0.015, 0.012, -0.008, 0.018],
            "vrp_structural": 0.95,
        }

        spec.is_satisfied_by(aapl_metrics)

        # Should use direct returns, no proxy
        assert "correlation_via_proxy" not in aapl_metrics
        assert "portfolio_rho" in aapl_metrics


class TestFuturesProxyCorrelationIntegration:
    """Integration tests for futures in full screening pipeline."""

    def test_futures_appear_in_screening_with_proxy_correlation(self):
        """Test that futures appear in screening candidates using proxy correlation."""
        # Portfolio with SPY-heavy exposure
        portfolio_returns = np.array([0.01, -0.02, 0.015, -0.01, 0.02] * 8)  # 40 days

        # Create uncorrelated GLD returns (use sine wave pattern, different phase)
        gld_returns = np.array([0.002 * np.sin(i * 0.5) for i in range(40)])

        raw_data = {
            "/ES": {
                "symbol": "/ES",
                "price": 5850.0,
                "iv": 15.0,
                "hv252": 18.0,
                "hv20": 12.0,
                "returns": [],  # No direct returns
                "vrp_structural": 0.90,  # Above threshold
                "sector": "Index",
                "atm_volume": 10000,
                "call_bid": 50.0,
                "call_ask": 50.5,
                "put_bid": 49.5,
                "put_ask": 50.0,
            },
            "SPY": {
                "symbol": "SPY",
                "price": 605.0,
                "iv": 12.0,
                "hv252": 19.0,
                "hv20": 10.0,
                "returns": list(portfolio_returns),  # Same as portfolio
                "vrp_structural": 0.90,
                "sector": "Index",
                "atm_volume": 50000,
                "call_bid": 8.0,
                "call_ask": 8.1,
                "put_bid": 7.9,
                "put_ask": 8.0,
            },
            "/GC": {
                "symbol": "/GC",
                "price": 2650.0,
                "iv": 18.0,
                "hv252": 15.0,
                "hv20": 11.0,
                "returns": [],  # No direct returns
                "vrp_structural": 1.20,  # Above threshold
                "sector": "Metals",
                "atm_volume": 5000,
                "call_bid": 20.0,
                "call_ask": 20.5,
                "put_bid": 19.5,
                "put_ask": 20.0,
            },
            "GLD": {
                "symbol": "GLD",
                "price": 413.0,
                "iv": 16.0,
                "hv252": 14.0,
                "hv20": 10.0,
                # Low correlation with SPY-heavy portfolio (sine wave pattern)
                "returns": list(gld_returns),
                "vrp_structural": 1.15,
                "sector": "Metals",
                "atm_volume": 8000,
                "call_bid": 5.0,
                "call_ask": 5.1,
                "put_bid": 4.9,
                "put_ask": 5.0,
            },
        }

        config = ScreenerConfig(
            limit=None,
            min_vrp_structural=None,
            exclude_sectors=None,
            allow_illiquid=True,
        )

        rules = {
            "vrp_structural_threshold": 0.85,
            "hv_floor_percent": 5.0,
            "max_portfolio_correlation": 0.70,
            "min_atm_volume": 500,
            "max_slippage_pct": 0.05,
        }

        market_config = {}

        candidates, counters = apply_specifications(
            raw_data, config, rules, market_config, portfolio_returns=portfolio_returns
        )

        # Assertions
        candidate_symbols = [c["symbol"] for c in candidates]

        # /ES should be REJECTED: uses SPY proxy, high correlation with SPY-heavy portfolio
        assert "/ES" not in candidate_symbols

        # /GC should be ALLOWED: uses GLD proxy, low correlation with SPY-heavy portfolio
        assert "/GC" in candidate_symbols

        # Verify /GC has proxy correlation metadata
        gc_candidate = next(c for c in candidates if c["symbol"] == "/GC")
        assert "portfolio_rho" in gc_candidate
        assert gc_candidate.get("correlation_via_proxy") is True
        assert abs(gc_candidate["portfolio_rho"]) <= 0.70

    def test_futures_rejected_by_high_correlation_via_proxy(self):
        """Test that /ES is rejected when portfolio is SPY-heavy (macro concentration risk)."""
        # SPY-like returns (high correlation scenario)
        portfolio_returns = np.array([0.01, -0.02, 0.015, -0.01, 0.02] * 8)

        raw_data = {
            "/ES": {
                "symbol": "/ES",
                "price": 5850.0,
                "iv": 15.0,
                "hv252": 18.0,
                "hv20": 12.0,
                "returns": [],
                "vrp_structural": 0.90,  # Above threshold, good VRP
                "sector": "Index",
                "atm_volume": 10000,
                "call_bid": 50.0,
                "call_ask": 50.5,
                "put_bid": 49.5,
                "put_ask": 50.0,
            },
            "SPY": {
                "symbol": "SPY",
                "price": 605.0,
                "iv": 12.0,
                "hv252": 19.0,
                "hv20": 10.0,
                "returns": list(portfolio_returns),  # Identical to portfolio
                "vrp_structural": 0.90,  # Above threshold
                "sector": "Index",
                "atm_volume": 50000,
                "call_bid": 8.0,
                "call_ask": 8.1,
                "put_bid": 7.9,
                "put_ask": 8.0,
            },
        }

        config = ScreenerConfig(
            limit=None,
            min_vrp_structural=None,
            exclude_sectors=None,
            allow_illiquid=True,
        )

        rules = {
            "vrp_structural_threshold": 0.85,
            "hv_floor_percent": 5.0,
            "max_portfolio_correlation": 0.70,
            "min_atm_volume": 500,
            "max_slippage_pct": 0.05,
        }

        market_config = {}

        candidates, counters = apply_specifications(
            raw_data, config, rules, market_config, portfolio_returns=portfolio_returns
        )

        # /ES should be rejected due to high correlation via SPY proxy
        candidate_symbols = [c["symbol"] for c in candidates]
        assert "/ES" not in candidate_symbols

        # Note: counter tracking - correlation filter removes from candidates silently
        # Just verify /ES was filtered out (already asserted above)

    def test_futures_allowed_with_low_correlation_portfolio(self):
        """Test that /ES passes when portfolio is gold-heavy (low correlation)."""
        # Orthogonal pattern - low correlation
        portfolio_returns = np.array([0.002 * np.sin(i * 0.5) for i in range(40)])
        spy_returns = np.array([0.01, -0.02, 0.015, -0.01, 0.02] * 8)

        raw_data = {
            "/ES": {
                "symbol": "/ES",
                "price": 5850.0,
                "iv": 15.0,
                "hv252": 18.0,
                "hv20": 12.0,
                "returns": [],
                "vrp_structural": 0.90,
                "sector": "Index",
                "atm_volume": 10000,
                "call_bid": 50.0,
                "call_ask": 50.5,
                "put_bid": 49.5,
                "put_ask": 50.0,
            },
            "SPY": {
                "symbol": "SPY",
                "price": 605.0,
                "iv": 12.0,
                "hv252": 19.0,
                "hv20": 10.0,
                "returns": list(spy_returns),  # Different from portfolio
                "vrp_structural": 0.90,
                "sector": "Index",
                "atm_volume": 50000,
                "call_bid": 8.0,
                "call_ask": 8.1,
                "put_bid": 7.9,
                "put_ask": 8.0,
            },
        }

        config = ScreenerConfig(
            limit=None,
            min_vrp_structural=None,
            exclude_sectors=None,
            allow_illiquid=True,
        )

        rules = {
            "vrp_structural_threshold": 0.85,
            "hv_floor_percent": 5.0,
            "max_portfolio_correlation": 0.70,
            "min_atm_volume": 500,
            "max_slippage_pct": 0.05,
        }

        market_config = {}

        candidates, counters = apply_specifications(
            raw_data, config, rules, market_config, portfolio_returns=portfolio_returns
        )

        # /ES should be ALLOWED: SPY proxy has low correlation with gold-heavy portfolio
        candidate_symbols = [c["symbol"] for c in candidates]
        assert "/ES" in candidate_symbols

        # Verify correlation metadata
        es_candidate = next(c for c in candidates if c["symbol"] == "/ES")
        assert "portfolio_rho" in es_candidate
        assert abs(es_candidate["portfolio_rho"]) <= 0.70

    def test_multiple_futures_with_different_correlations(self):
        """Test screening multiple futures with varying correlations."""
        # SPY-heavy portfolio
        portfolio_returns = np.array([0.01, -0.02, 0.015, -0.01, 0.02] * 8)

        # Uncorrelated returns for GLD and FXE
        gld_returns = np.array([0.002 * np.sin(i * 0.5) for i in range(40)])
        fxe_returns = np.array([0.001 * np.cos(i * 0.3) for i in range(40)])

        raw_data = {
            "/ES": {
                "symbol": "/ES",
                "returns": [],
                "vrp_structural": 0.90,
                "price": 5850.0,
                "iv": 15.0,
                "hv252": 18.0,
                "hv20": 12.0,
                "sector": "Index",
                "atm_volume": 10000,
                "call_bid": 50.0,
                "call_ask": 50.5,
                "put_bid": 49.5,
                "put_ask": 50.0,
            },
            "SPY": {
                "symbol": "SPY",
                "returns": list(portfolio_returns),  # High correlation
                "vrp_structural": 0.90,
                "price": 605.0,
                "iv": 12.0,
                "hv252": 19.0,
                "hv20": 10.0,
                "sector": "Index",
                "atm_volume": 50000,
                "call_bid": 8.0,
                "call_ask": 8.1,
                "put_bid": 7.9,
                "put_ask": 8.0,
            },
            "/GC": {
                "symbol": "/GC",
                "returns": [],
                "vrp_structural": 1.20,
                "price": 2650.0,
                "iv": 18.0,
                "hv252": 15.0,
                "hv20": 11.0,
                "sector": "Metals",
                "atm_volume": 5000,
                "call_bid": 20.0,
                "call_ask": 20.5,
                "put_bid": 19.5,
                "put_ask": 20.0,
            },
            "GLD": {
                "symbol": "GLD",
                "returns": list(gld_returns),  # Low correlation
                "vrp_structural": 1.15,
                "price": 413.0,
                "iv": 16.0,
                "hv252": 14.0,
                "hv20": 10.0,
                "sector": "Metals",
                "atm_volume": 8000,
                "call_bid": 5.0,
                "call_ask": 5.1,
                "put_bid": 4.9,
                "put_ask": 5.0,
            },
            "/6E": {
                "symbol": "/6E",
                "returns": [],
                "vrp_structural": 1.10,
                "price": 108.0,
                "iv": 12.0,
                "hv252": 10.0,
                "hv20": 9.0,
                "sector": "FX",
                "atm_volume": 3000,
                "call_bid": 0.5,
                "call_ask": 0.55,
                "put_bid": 0.45,
                "put_ask": 0.5,
            },
            "FXE": {
                "symbol": "FXE",
                "returns": list(fxe_returns),  # Low correlation
                "vrp_structural": 1.05,
                "price": 108.5,
                "iv": 10.0,
                "hv252": 9.0,
                "hv20": 8.0,
                "sector": "FX",
                "atm_volume": 4000,
                "call_bid": 1.0,
                "call_ask": 1.05,
                "put_bid": 0.95,
                "put_ask": 1.0,
            },
        }

        config = ScreenerConfig(
            limit=None,
            min_vrp_structural=None,
            exclude_sectors=None,
            allow_illiquid=True,
        )

        rules = {
            "vrp_structural_threshold": 0.85,
            "hv_floor_percent": 5.0,
            "max_portfolio_correlation": 0.70,
            "min_atm_volume": 500,
            "max_slippage_pct": 0.05,
        }

        market_config = {}

        candidates, counters = apply_specifications(
            raw_data, config, rules, market_config, portfolio_returns=portfolio_returns
        )

        candidate_symbols = [c["symbol"] for c in candidates]

        # Expected results:
        # /ES: HIGH correlation via SPY → REJECTED
        # /GC: LOW correlation via GLD → ALLOWED
        # /6E: LOW correlation via FXE → ALLOWED

        assert "/ES" not in candidate_symbols  # Rejected (high correlation)
        assert "/GC" in candidate_symbols  # Allowed (low correlation)
        assert "/6E" in candidate_symbols  # Allowed (low correlation)

        # Verify all allowed futures have proxy flag
        for symbol in ["/GC", "/6E"]:
            candidate = next(c for c in candidates if c["symbol"] == symbol)
            assert candidate.get("correlation_via_proxy") is True
            assert "portfolio_rho" in candidate


class TestFuturesProxyEdgeCases:
    """Edge case tests for futures proxy correlation."""

    def test_no_portfolio_returns_allows_all_futures(self):
        """Test that futures pass when no portfolio exists (no correlation guard)."""
        raw_data = {
            "/ES": {
                "symbol": "/ES",
                "returns": [],
                "vrp_structural": 0.90,
                "price": 5850.0,
                "iv": 15.0,
                "hv252": 18.0,
                "hv20": 12.0,
                "sector": "Index",
                "atm_volume": 10000,
                "call_bid": 50.0,
                "call_ask": 50.5,
                "put_bid": 49.5,
                "put_ask": 50.0,
            },
        }

        spec = CorrelationSpec(portfolio_returns=None, max_correlation=0.70, raw_data=raw_data)

        es_metrics = {"symbol": "/ES", "returns": [], "vrp_structural": 0.90}

        result = spec.is_satisfied_by(es_metrics)

        # Should pass without correlation check
        assert result is True

    def test_empty_portfolio_returns_allows_all_futures(self):
        """Test that empty portfolio returns list allows all futures."""
        raw_data = {
            "/ES": {
                "symbol": "/ES",
                "returns": [],
                "vrp_structural": 0.90,
                "price": 5850.0,
                "iv": 15.0,
                "hv252": 18.0,
                "hv20": 12.0,
                "sector": "Index",
                "atm_volume": 10000,
                "call_bid": 50.0,
                "call_ask": 50.5,
                "put_bid": 49.5,
                "put_ask": 50.0,
            },
        }

        spec = CorrelationSpec(
            portfolio_returns=np.array([]), max_correlation=0.70, raw_data=raw_data
        )

        es_metrics = {"symbol": "/ES", "returns": [], "vrp_structural": 0.90}

        result = spec.is_satisfied_by(es_metrics)

        # Should pass without correlation check
        assert result is True

    def test_proxy_returns_empty_list_rejected(self):
        """Test that futures are rejected if proxy has empty returns."""
        portfolio_returns = np.array([0.01, -0.02, 0.015, -0.01, 0.02])

        raw_data = {
            "/ES": {
                "symbol": "/ES",
                "returns": [],
                "vrp_structural": 0.90,
            },
            "SPY": {
                "symbol": "SPY",
                "returns": [],  # Proxy also has no data
                "vrp_structural": 0.63,
            },
        }

        spec = CorrelationSpec(portfolio_returns, max_correlation=0.70, raw_data=raw_data)

        es_metrics = {"symbol": "/ES", "returns": [], "vrp_structural": 0.90}

        result = spec.is_satisfied_by(es_metrics)

        # Should reject due to no usable data
        assert result is False
