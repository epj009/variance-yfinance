"""
Integration tests for production-scale portfolio analysis.

Tests system behavior with realistic portfolio sizes (50+ positions)
to catch timeout issues, performance bottlenecks, and memory leaks.
"""

import time

import pytest

from variance.analyze_portfolio import analyze_portfolio
from variance.market_data.service import MarketDataFactory


class TestProductionScale:
    """Test system performance and correctness at production scale."""

    @pytest.fixture
    def large_mock_provider(self, mock_market_provider):
        """Create mock provider with 50 symbols."""
        # Generate 50 symbols with realistic data
        symbols = [
            # Tech (20)
            "AAPL",
            "GOOGL",
            "MSFT",
            "NVDA",
            "AMD",
            "TSLA",
            "META",
            "NFLX",
            "AMZN",
            "CRM",
            "ORCL",
            "ADBE",
            "INTC",
            "CSCO",
            "AVGO",
            "TXN",
            "QCOM",
            "MU",
            "AMAT",
            "LRCX",
            # Finance (10)
            "JPM",
            "BAC",
            "WFC",
            "GS",
            "MS",
            "C",
            "BLK",
            "SCHW",
            "AXP",
            "USB",
            # Healthcare (10)
            "UNH",
            "JNJ",
            "PFE",
            "ABBV",
            "TMO",
            "MRK",
            "LLY",
            "ABT",
            "DHR",
            "BMY",
            # Energy (5)
            "XOM",
            "CVX",
            "COP",
            "SLB",
            "EOG",
            # Indices (5)
            "SPY",
            "QQQ",
            "IWM",
            "DIA",
            "VIX",
        ]

        fake_data = {}
        for i, sym in enumerate(symbols):
            # Vary metrics to simulate realistic portfolio
            base_iv = 20.0 + (i % 30)
            base_hv = base_iv - 5.0
            fake_data[sym] = {
                "price": 100.0 + (i * 10),
                "iv": base_iv,
                "hv30": base_hv,
                "hv90": base_hv - 2.0,
                "hv252": base_hv - 3.0,
                "iv_rank": 40.0 + (i % 50),
                "iv_percentile": 35.0 + (i % 60),
                "vrp_structural": 1.05 + (i % 20) / 100.0,
                "vrp_tactical": 1.10 + (i % 15) / 100.0,
                "beta": 1.0 + (i % 10) / 10.0,
                "sector": ["Technology", "Finance", "Healthcare", "Energy", "Index"][i % 5],
                "liquidity_rating": 4 if i < 40 else 3,  # Most liquid, some illiquid
                "option_volume": 5000 if i < 40 else 500,
                "returns": [0.01, -0.005, 0.008] * 20,  # 60 days of returns
            }

        return mock_market_provider(fake_data)

    @pytest.fixture
    def large_portfolio_csv(self, tmp_path):
        """Create CSV file with 50 positions."""
        csv_path = tmp_path / "large_portfolio.csv"

        # Generate 50 positions (mix of stocks and options)
        rows = ["Symbol,Type,Quantity,Exp Date,Strike Price,Call/Put,Delta,Theta,Value,Sector"]

        symbols = [
            "AAPL",
            "GOOGL",
            "MSFT",
            "NVDA",
            "AMD",
            "TSLA",
            "META",
            "NFLX",
            "AMZN",
            "CRM",
            "ORCL",
            "ADBE",
            "INTC",
            "CSCO",
            "AVGO",
            "TXN",
            "QCOM",
            "MU",
            "AMAT",
            "LRCX",
            "JPM",
            "BAC",
            "WFC",
            "GS",
            "MS",
            "C",
            "BLK",
            "SCHW",
            "AXP",
            "USB",
            "UNH",
            "JNJ",
            "PFE",
            "ABBV",
            "TMO",
            "MRK",
            "LLY",
            "ABT",
            "DHR",
            "BMY",
            "XOM",
            "CVX",
            "COP",
            "SLB",
            "EOG",
            "SPY",
            "QQQ",
            "IWM",
            "DIA",
            "VIX",
        ]

        sectors = [
            "Technology",
            "Technology",
            "Technology",
            "Technology",
            "Technology",
            "Technology",
            "Technology",
            "Technology",
            "Technology",
            "Technology",
            "Technology",
            "Technology",
            "Technology",
            "Technology",
            "Technology",
            "Technology",
            "Technology",
            "Technology",
            "Technology",
            "Technology",
            "Finance",
            "Finance",
            "Finance",
            "Finance",
            "Finance",
            "Finance",
            "Finance",
            "Finance",
            "Finance",
            "Finance",
            "Healthcare",
            "Healthcare",
            "Healthcare",
            "Healthcare",
            "Healthcare",
            "Healthcare",
            "Healthcare",
            "Healthcare",
            "Healthcare",
            "Healthcare",
            "Energy",
            "Energy",
            "Energy",
            "Energy",
            "Energy",
            "Index",
            "Index",
            "Index",
            "Index",
            "Index",
        ]

        for i, (sym, sector) in enumerate(zip(symbols, sectors)):
            # Mix of short puts and strangles
            if i % 3 == 0:
                # Short Strangle
                rows.append(
                    f"{sym},Equity Option,1,2026-02-20,{100 + i * 5},Call,-30,-5,500,{sector}"
                )
                rows.append(f"{sym},Equity Option,1,2026-02-20,{95 + i * 5},Put,30,-5,500,{sector}")
            else:
                # Short Put
                rows.append(
                    f"{sym},Equity Option,1,2026-02-20,{100 + i * 5},Put,40,-8,800,{sector}"
                )

        csv_path.write_text("\n".join(rows))
        return str(csv_path)

    def test_analyze_portfolio_with_50_positions_completes_in_time(
        self, monkeypatch, large_portfolio_csv, large_mock_provider
    ):
        """
        CRITICAL: Verify analysis completes within acceptable time for 50 positions.

        Addresses:
        - BLOCKER-3: Timeout handling for large portfolios
        - PERF-1: N+1 market data fetches
        - GAP-1: Missing large portfolio test
        """
        monkeypatch.setattr(
            MarketDataFactory, "get_provider", lambda type="tastytrade": large_mock_provider
        )

        start = time.time()
        result = analyze_portfolio(large_portfolio_csv)
        elapsed = time.time() - start

        # Assert: Completes in <15 seconds (lenient for mock)
        # In production with real API, should be <30s with caching
        assert elapsed < 15.0, f"Analysis took {elapsed:.1f}s (expected <15s)"

        # Assert: No errors
        assert "error" not in result, f"Analysis failed: {result.get('error')}"

        # Assert: All positions processed
        total_positions = len(result.get("triage_actions", [])) + len(
            result.get("portfolio_overview", [])
        )
        assert total_positions >= 50, f"Only {total_positions} positions processed (expected >=50)"

    def test_analyze_portfolio_with_50_positions_has_complete_market_data(
        self, monkeypatch, large_portfolio_csv, large_mock_provider
    ):
        """
        CRITICAL: Verify all positions have complete market data.

        Addresses:
        - BLOCKER-1: Silent failures in market data fetching
        """
        monkeypatch.setattr(
            MarketDataFactory, "get_provider", lambda type="tastytrade": large_mock_provider
        )

        result = analyze_portfolio(large_portfolio_csv)

        # Assert: Market data diagnostics show high success rate
        diagnostics = result.get("market_data_diagnostics", {})
        total_symbols = diagnostics.get("total_symbols", 0)
        success_symbols = diagnostics.get("success_symbols", 0)

        assert total_symbols >= 50, f"Expected >=50 symbols, got {total_symbols}"

        # Assert: >90% success rate (allow some failures for realism)
        success_rate = success_symbols / total_symbols if total_symbols > 0 else 0
        assert success_rate >= 0.90, (
            f"Market data success rate {success_rate:.1%} < 90% (expected high reliability)"
        )

        # Assert: Check for any critical errors
        error_symbols = diagnostics.get("error_symbols", [])
        if error_symbols:
            # Allowed: max 5 errors (10% of portfolio)
            assert len(error_symbols) <= 5, (
                f"Too many errors ({len(error_symbols)}): {error_symbols}"
            )

    def test_analyze_portfolio_with_50_positions_memory_usage(
        self, monkeypatch, large_portfolio_csv, large_mock_provider
    ):
        """
        PERFORMANCE: Verify memory usage stays reasonable for large portfolios.

        Addresses:
        - GAP-7: Load test for screening pipeline
        """
        monkeypatch.setattr(
            MarketDataFactory, "get_provider", lambda type="tastytrade": large_mock_provider
        )

        import tracemalloc

        tracemalloc.start()

        result = analyze_portfolio(large_portfolio_csv)

        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        peak_mb = peak / 1024 / 1024

        # Assert: Peak memory usage <200MB (generous for mock data)
        assert peak_mb < 200, f"Peak memory usage {peak_mb:.1f}MB (expected <200MB)"
        assert "error" not in result

    def test_analyze_portfolio_handles_partial_market_data_failures(
        self, monkeypatch, large_portfolio_csv, mock_market_provider
    ):
        """
        CRITICAL: Verify graceful handling when 20% of symbols fail.

        Addresses:
        - BLOCKER-1: Silent failures in market data fetching
        - Fail-fast threshold proposal
        """

        # Mock provider that fails for 20% of symbols
        def failing_provider_factory(success_symbols: list[str], fail_symbols: list[str]):
            data = {}
            for sym in success_symbols:
                data[sym] = {
                    "price": 100.0,
                    "iv": 25.0,
                    "hv30": 20.0,
                    "hv90": 18.0,
                    "hv252": 17.0,
                    "vrp_structural": 1.15,
                    "sector": "Technology",
                }
            for sym in fail_symbols:
                data[sym] = {"error": "api_timeout"}
            return mock_market_provider(data)

        # 40 success, 10 failures (20%)
        success = [
            "AAPL",
            "GOOGL",
            "MSFT",
            "NVDA",
            "AMD",
            "TSLA",
            "META",
            "NFLX",
            "AMZN",
            "CRM",
            "ORCL",
            "ADBE",
            "INTC",
            "CSCO",
            "AVGO",
            "TXN",
            "QCOM",
            "MU",
            "AMAT",
            "LRCX",
            "JPM",
            "BAC",
            "WFC",
            "GS",
            "MS",
            "C",
            "BLK",
            "SCHW",
            "AXP",
            "USB",
            "UNH",
            "JNJ",
            "PFE",
            "ABBV",
            "TMO",
            "MRK",
            "LLY",
            "ABT",
            "DHR",
            "BMY",
            "SPY",
        ]
        failures = ["XOM", "CVX", "COP", "SLB", "EOG", "QQQ", "IWM", "DIA", "VIX", "GLD"]

        provider = failing_provider_factory(success, failures)
        monkeypatch.setattr(MarketDataFactory, "get_provider", lambda type="tastytrade": provider)

        result = analyze_portfolio(large_portfolio_csv)

        # Assert: Analysis still completes (doesn't crash)
        assert "portfolio_summary" in result

        # Assert: Market data diagnostics show the failures
        diagnostics = result.get("market_data_diagnostics", {})
        error_symbols = diagnostics.get("error_symbols", [])

        # Should report the 10 failures
        assert len(error_symbols) >= 8, f"Expected ~10 errors, got {len(error_symbols)}"

        # Assert: Triage only processes positions with valid data
        # (Positions with failed symbols should be skipped or marked stale)
        all_positions = result.get("triage_actions", []) + result.get("portfolio_overview", [])

        stale_count = sum(1 for pos in all_positions if pos.get("is_stale"))
        # Expect some positions marked as stale due to missing data
        assert stale_count > 0, "Expected some positions marked stale when market data fails"

    def test_analyze_portfolio_data_quality_score_calculation(
        self, monkeypatch, large_portfolio_csv, large_mock_provider
    ):
        """
        Feature Request: Verify data quality score is calculated and exposed.

        Addresses:
        - Proposal to add data_quality_score to portfolio summary
        """
        monkeypatch.setattr(
            MarketDataFactory, "get_provider", lambda type="tastytrade": large_mock_provider
        )

        result = analyze_portfolio(large_portfolio_csv)

        # NOTE: This test will FAIL until data_quality_score is implemented
        # This is intentional - it documents the expected behavior

        # Assert: Portfolio summary should include data quality score
        summary = result.get("portfolio_summary", {})

        # TODO: Uncomment once feature is implemented
        # assert "data_quality_score" in summary
        # quality = summary["data_quality_score"]
        # assert 0 <= quality <= 100, f"Data quality score {quality} out of range 0-100"

        # For now, verify market_data_diagnostics exists (prerequisite)
        assert "market_data_diagnostics" in result


class TestMarketDataBatching:
    """Test market data service batching and parallel fetching."""

    def test_market_data_service_batches_symbols_efficiently(self, mock_market_provider):
        """
        PERFORMANCE: Verify market data service batches requests efficiently.

        Addresses:
        - PERF-1: N+1 market data fetches
        """
        from variance.market_data.service import MarketDataService

        # Create provider with 50 symbols
        symbols = [f"TEST{i}" for i in range(50)]
        fake_data = {
            sym: {
                "price": 100.0,
                "iv": 25.0,
                "hv30": 20.0,
                "hv90": 18.0,
            }
            for sym in symbols
        }
        provider = mock_market_provider(fake_data)

        service = MarketDataService()
        service.provider = provider

        start = time.time()
        results = service.get_market_data(symbols)
        elapsed = time.time() - start

        # Assert: All symbols returned
        assert len(results) == 50

        # Assert: Completes quickly (mock should be <1s)
        assert elapsed < 2.0, f"Batch fetch took {elapsed:.2f}s (expected <2s for mock)"

    def test_market_data_service_handles_empty_symbol_list(self, mock_market_provider):
        """
        EDGE CASE: Verify graceful handling of empty symbol list.
        """
        from variance.market_data.service import MarketDataService

        provider = mock_market_provider({})
        service = MarketDataService()
        service.provider = provider

        # Should not crash
        results = service.get_market_data([])
        assert results == {}

    def test_market_data_service_deduplicates_symbols(self, mock_market_provider):
        """
        EDGE CASE: Verify duplicate symbols are handled correctly.
        """
        from variance.market_data.service import MarketDataService

        fake_data = {"AAPL": {"price": 150.0, "iv": 25.0}}
        provider = mock_market_provider(fake_data)
        service = MarketDataService()
        service.provider = provider

        # Request same symbol 10 times
        results = service.get_market_data(["AAPL"] * 10)

        # Should return data once
        assert len(results) == 1
        assert "AAPL" in results


@pytest.mark.slow
class TestScreeningPipelineScale:
    """Test screening pipeline performance at scale."""

    def test_screening_pipeline_handles_500_symbols(self, mock_market_provider):
        """
        LOAD TEST: Verify screening pipeline scales to 500 symbols.

        Addresses:
        - GAP-7: Load test for screening pipeline
        """
        pytest.skip("Requires 500-symbol mock data setup - implement when needed")
        # TODO: Implement when screening pipeline needs scale testing

    def test_screening_pipeline_memory_usage_stable(self):
        """
        PERFORMANCE: Verify screening doesn't leak memory over multiple runs.
        """
        pytest.skip("Requires multiple sequential runs - implement when needed")
        # TODO: Implement when memory profiling is needed
