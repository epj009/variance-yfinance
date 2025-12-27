"""
Comprehensive test suite for scripts/get_market_data.py
Updated for decoupled architecture and robust math.
"""

import time
from unittest.mock import Mock, patch

import pandas as pd
import pytest

from variance import get_market_data
from variance.get_market_data import (
    MarketCache,
    _fallback_to_cached_market_data,
    _get_cached_market_data,
    calculate_hv,
    get_current_iv,
    get_price,
    normalize_iv,
)
from variance.market_data import helpers as md_helpers

# ============================================================================
# TEST CLASS 1: normalize_iv() - CRITICAL PRIORITY
# ============================================================================


class TestNormalizeIV:
    """
    Unit tests for IV normalization - CRITICAL for trading accuracy.
    """

    def test_normalize_iv_clear_percentage(self):
        """IV > 1.5 is always treated as percentage format."""
        iv, warning = normalize_iv(32.5, hv_context=None)
        assert iv == 32.5
        assert warning is None

    def test_normalize_iv_decimal_to_percent_no_context(self):
        """Decimal IV (0.325) converted to percentage (32.5%) without context."""
        iv, warning = normalize_iv(0.325, hv_context=None)
        assert iv == 32.5
        assert warning == "iv_scale_assumed_decimal"

    def test_normalize_iv_uses_distance_to_context(self):
        """
        Case: IV=0.25, HV=20.0.
        Scaled: 25.0 (dist 5.0)
        Unscaled: 0.25 (dist 19.75)
        Should scale.
        """
        iv, warning = normalize_iv(0.25, hv_context=20.0)
        assert iv == 25.0
        assert warning == "iv_scale_corrected"

    def test_normalize_iv_handles_ambiguous_correctly(self):
        """
        Case: IV=0.5, HV=5.0.
        Scaled: 50.0 (dist 45.0)
        Unscaled: 0.5 (dist 4.5)
        Clinical Result: 0.5 is closer to context. No scaling.
        """
        iv, warning = normalize_iv(0.5, hv_context=5.0)
        assert iv == 0.5
        assert warning is None

    def test_normalize_iv_corrects_high_decimal(self):
        """Boundary: IV=1.0 treated as decimal (100%) when context is 15%."""
        iv, warning = normalize_iv(1.0, hv_context=15.0)
        assert iv == 100.0
        assert warning == "iv_scale_corrected"

    def test_normalize_iv_handles_low_vol_context(self):
        """
        Case: IV=1.5, HV=5.0.
        Log-Dist Unscaled: |log(1.5/5.0)| = 1.2
        Log-Dist Scaled:   |log(150/5.0)| = 3.4
        Result: 1.5 is closer. No scaling.
        """
        iv, warning = normalize_iv(1.5, hv_context=5.0)
        assert iv == 1.5
        assert warning is None

    def test_normalize_iv_zero_or_none(self):
        iv, warning = normalize_iv(0.0, hv_context=10.0)
        assert iv == 0.0
        assert warning == "iv_zero_or_none"


# ============================================================================
# TEST CLASS 2: MarketCache - HIGH PRIORITY
# ============================================================================


class TestMarketCache:
    """Test the SQLite caching engine."""

    def test_cache_set_and_get(self, temp_cache_db):
        """Basic set/get functionality."""
        cache = MarketCache(str(temp_cache_db))
        test_data = {"iv": 30.5, "hv": 25.0}
        cache.set("test_key", test_data, ttl_seconds=3600)
        assert cache.get("test_key") == test_data

    def test_cache_miss_returns_none(self, temp_cache_db):
        """Missing key returns None."""
        cache = MarketCache(str(temp_cache_db))
        assert cache.get("nonexistent") is None

    def test_cache_handles_invalid_json(self, temp_cache_db):
        cache = MarketCache(str(temp_cache_db))
        conn = cache._get_conn()
        conn.execute(
            "INSERT OR REPLACE INTO cache (key, value, expiry) VALUES (?, ?, ?)",
            ("bad_json", "{", int(time.time()) + 3600),
        )
        conn.commit()

        assert cache.get("bad_json") is None
        assert cache.get_any("bad_json") is None

    def test_cache_close_and_close_all(self, temp_cache_db):
        cache = MarketCache(str(temp_cache_db))
        cache.get("touch")
        cache.close()
        cache.get("touch")
        cache.close_all()

    def test_cache_set_ignores_none(self, temp_cache_db):
        cache = MarketCache(str(temp_cache_db))
        cache.set("none_key", None, ttl_seconds=3600)

        assert cache.get("none_key") is None

    def test_cache_health_reports_connections(self, temp_cache_db):
        cache = MarketCache(str(temp_cache_db))
        cache.get("touch")
        health = cache.health()

        assert health["active_connections"] >= 1
        assert health["total_opened"] >= 1

        cache.close_all()
        health = cache.health()

        assert health["active_connections"] == 0
        assert health["leaked_connections"] == 0


class TestCacheHelpers:
    def test_get_cached_market_data_prefers_market_data_key(self, temp_cache_db):
        cache = MarketCache(str(temp_cache_db))
        cache.set("market_data_AAPL", {"price": 100}, ttl_seconds=3600)
        cache.set("md_AAPL", {"price": 200}, ttl_seconds=3600)

        result = _get_cached_market_data(cache, "AAPL", allow_expired=False)

        assert result == {"price": 100}

    def test_fallback_to_cached_market_data_sets_warning(self, temp_cache_db, monkeypatch):
        cache = MarketCache(str(temp_cache_db))
        cache.set("md_AAPL", {"price": 150}, ttl_seconds=-1)

        messages = []

        def fake_warning(*args, **_kwargs):
            messages.append(args)

        monkeypatch.setattr(md_helpers.logger, "warning", fake_warning)

        result = _fallback_to_cached_market_data(
            cache,
            "AAPL",
            warning="yfinance_unavailable_cached",
            provider="yfinance",
            reason="price_unavailable",
        )

        assert result["warning"] == "yfinance_unavailable_cached"
        assert result["data_source"] == "yfinance"
        assert messages == [
            (
                "provider_fallback provider=%s symbol=%s cached=%s reason=%s",
                "yfinance",
                "AAPL",
                True,
                "price_unavailable",
            )
        ]

    def test_get_cached_market_data_allows_expired(self, temp_cache_db):
        cache = MarketCache(str(temp_cache_db))
        cache.set("md_AAPL", {"price": 250}, ttl_seconds=-1)

        result = _get_cached_market_data(cache, "AAPL", allow_expired=True)

        assert result == {"price": 250}


class TestGetPrice:
    def test_get_price_uses_cache(self, temp_cache_db):
        cache = MarketCache(str(temp_cache_db))
        cache.set("price_AAPL", 123.45, ttl_seconds=3600)
        ticker = Mock()

        result = get_price(ticker, "AAPL", cache=cache)

        assert result == (123.45, True)

    def test_get_price_falls_back_to_fast_info(self, temp_cache_db):
        cache = MarketCache(str(temp_cache_db))
        cache.set("price_AAPL", "bad", ttl_seconds=3600)

        ticker = Mock()
        ticker.fast_info = Mock()
        ticker.fast_info.last_price = 200.0

        result = get_price(ticker, "AAPL", cache=cache)

        assert result == (200.0, False)

    def test_get_price_handles_empty_sequence(self, temp_cache_db):
        cache = MarketCache(str(temp_cache_db))
        ticker = Mock()
        ticker.fast_info = Mock()
        ticker.fast_info.last_price = []

        result = get_price(ticker, "AAPL", cache=cache)

        assert result is None

    def test_get_price_handles_sequence_with_value(self, temp_cache_db):
        cache = MarketCache(str(temp_cache_db))
        ticker = Mock()
        ticker.fast_info = Mock()
        ticker.fast_info.last_price = [321.0]

        result = get_price(ticker, "AAPL", cache=cache)

        assert result == (321.0, False)


class TestCalculateHV:
    def test_calculate_hv_insufficient_history(self, temp_cache_db, monkeypatch):
        cache = MarketCache(str(temp_cache_db))
        ticker = Mock()
        ticker.history.return_value = pd.DataFrame({"Close": [100.0] * 10})

        monkeypatch.setattr(get_market_data, "HV_MIN_HISTORY_DAYS", 200)
        result = calculate_hv(ticker, "AAPL", cache=cache)

        assert result is None

    def test_calculate_hv_returns_metrics(self, temp_cache_db):
        cache = MarketCache(str(temp_cache_db))
        prices = pd.Series([100 + (i * 0.5) for i in range(260)])
        ticker = Mock()
        ticker.history.return_value = pd.DataFrame({"Close": prices})

        result = calculate_hv(ticker, "AAPL", cache=cache)

        assert result is not None
        assert "hv252" in result
        assert "hv20" in result
        assert "hv60" in result
        assert "hv20_stderr" in result
        assert "raw_returns" in result

    def test_calculate_hv_uses_cache(self, temp_cache_db):
        cache = MarketCache(str(temp_cache_db))
        cached = {"hv252": 12.0, "hv60": 10.0, "hv20": 8.0, "raw_returns": [0.1]}
        cache.set("hv_AAPL", cached, ttl_seconds=3600)
        ticker = Mock()

        result = calculate_hv(ticker, "AAPL", cache=cache)

        assert result == cached


# ============================================================================
# TEST CLASS 3: get_current_iv() - HIGH PRIORITY
# ============================================================================


class TestGetCurrentIV:
    """Test option chain IV extraction and gating."""

    def test_get_iv_happy_path(self, temp_cache_db, mock_ticker_factory, mock_option_chain):
        """Standard IV extraction from ATM options."""
        calls, puts = mock_option_chain
        ticker = mock_ticker_factory(
            options=["2025-02-15"], option_chain_calls=calls, option_chain_puts=puts
        )

        # Should return data dict
        result = get_current_iv(ticker, 150.0, "AAPL", hv_context=25.0)
        assert pytest.approx(result["iv"]) == 28.0
        assert result["atm_vol"] > 0

    def test_get_iv_rejects_illiquid(self, temp_cache_db, mock_ticker_factory):
        """Returns empty dict if no liquidity."""
        empty_df = pd.DataFrame({"bid": [0], "ask": [0]})
        ticker = mock_ticker_factory(option_chain_calls=empty_df, option_chain_puts=empty_df)
        result = get_current_iv(ticker, 150.0, "AAPL")
        assert result == {}

    def test_get_iv_no_options_returns_empty(self, temp_cache_db):
        cache = MarketCache(str(temp_cache_db))
        ticker = Mock()
        ticker.options = []

        result = get_current_iv(ticker, 150.0, "AAPL", cache=cache)

        assert result == {}

    def test_get_iv_uses_cache(self, temp_cache_db):
        """Cached IV is returned without API call."""
        cache = MarketCache(str(temp_cache_db))
        cached_value = {"iv": 28.5, "atm_vol": 1000}
        cache.set("iv_AAPL", cached_value, 3600)

        with patch.object(get_market_data, "cache", cache):
            ticker = Mock()
            ticker.options = []  # Should not be called
            result = get_current_iv(ticker, 150.0, "AAPL")
            assert result == cached_value

    def test_get_iv_uses_nearest_expiration_when_no_dte_match(self, temp_cache_db):
        cache = MarketCache(str(temp_cache_db))
        now = pd.Timestamp.now()
        early = (now + pd.Timedelta(days=10)).strftime("%Y-%m-%d")
        late = (now + pd.Timedelta(days=80)).strftime("%Y-%m-%d")

        calls = pd.DataFrame(
            {
                "strike": [100.0],
                "bid": [1.0],
                "ask": [1.1],
                "impliedVolatility": [0.25],
                "openInterest": [10],
                "volume": [5],
            }
        )
        puts = pd.DataFrame(
            {
                "strike": [100.0],
                "bid": [1.0],
                "ask": [1.1],
                "impliedVolatility": [0.25],
                "openInterest": [10],
                "volume": [5],
            }
        )

        chain = Mock()
        chain.calls = calls
        chain.puts = puts

        ticker = Mock()
        ticker.options = [early, late]
        ticker.option_chain = Mock(return_value=chain)

        result = get_current_iv(ticker, 100.0, "AAPL", cache=cache)

        ticker.option_chain.assert_called_once_with(early)
        assert result["iv"] > 0

    def test_get_iv_uses_dte_window_when_available(self, temp_cache_db):
        cache = MarketCache(str(temp_cache_db))
        now = pd.Timestamp.now()
        in_window = (now + pd.Timedelta(days=30)).strftime("%Y-%m-%d")
        out_window = (now + pd.Timedelta(days=80)).strftime("%Y-%m-%d")

        calls = pd.DataFrame(
            {
                "strike": [100.0],
                "bid": [1.0],
                "ask": [1.1],
                "impliedVolatility": [0.25],
                "openInterest": [10],
                "volume": [5],
            }
        )
        puts = pd.DataFrame(
            {
                "strike": [100.0],
                "bid": [1.0],
                "ask": [1.1],
                "impliedVolatility": [0.25],
                "openInterest": [10],
                "volume": [5],
            }
        )

        chain = Mock()
        chain.calls = calls
        chain.puts = puts

        ticker = Mock()
        ticker.options = [in_window, out_window]
        ticker.option_chain = Mock(return_value=chain)

        result = get_current_iv(ticker, 100.0, "AAPL", cache=cache)

        ticker.option_chain.assert_called_once_with(in_window)
        assert result["iv"] > 0

    def test_get_iv_returns_empty_when_chain_empty(self, temp_cache_db):
        cache = MarketCache(str(temp_cache_db))
        ticker = Mock()
        ticker.options = ["2025-02-15"]
        chain = Mock()
        chain.calls = pd.DataFrame()
        chain.puts = pd.DataFrame()
        ticker.option_chain = Mock(return_value=chain)

        result = get_current_iv(ticker, 150.0, "AAPL", cache=cache)

        assert result == {}

    def test_get_iv_safe_float_handles_bad_values(self, temp_cache_db):
        cache = MarketCache(str(temp_cache_db))
        calls = pd.DataFrame(
            {
                "strike": [100.0],
                "bid": [1.0],
                "ask": [1.1],
                "impliedVolatility": [0.25],
                "openInterest": [float("nan")],
                "volume": [None],
            }
        )
        puts = pd.DataFrame(
            {
                "strike": [100.0],
                "bid": [1.0],
                "ask": [1.1],
                "impliedVolatility": [0.25],
                "openInterest": ["bad"],
                "volume": ["bad"],
            }
        )

        chain = Mock()
        chain.calls = calls
        chain.puts = puts

        ticker = Mock()
        ticker.options = ["2025-02-15"]
        ticker.option_chain = Mock(return_value=chain)

        result = get_current_iv(ticker, 100.0, "AAPL", cache=cache)

        assert result["atm_vol"] == 0
        assert result["atm_oi"] == 0

    def test_get_iv_handles_exception(self, temp_cache_db):
        cache = MarketCache(str(temp_cache_db))

        class BadTicker:
            @property
            def options(self):
                raise RuntimeError("boom")

        result = get_current_iv(BadTicker(), 100.0, "AAPL", cache=cache)

        assert result == {}


class TestProcessSingleSymbolFallback:
    def test_returns_cached_data_on_yfinance_failure(self, temp_cache_db, monkeypatch):
        cache = MarketCache(str(temp_cache_db))
        cached_value = {
            "price": 101.0,
            "iv": 20.0,
            "hv252": 18.0,
            "hv20": 15.0,
        }
        cache.set("market_data_AAPL", cached_value, ttl_seconds=-1)

        monkeypatch.setattr(get_market_data, "is_market_open", lambda: True)
        monkeypatch.setattr(get_market_data, "get_price", lambda *_args, **_kwargs: None)

        symbol, data = get_market_data.process_single_symbol("AAPL", cache_instance=cache)

        assert symbol == "AAPL"
        assert data["price"] == 101.0
        assert data["warning"] == "yfinance_unavailable_cached"
        assert data["is_stale"] is True

    def test_market_closed_uses_stale_cache(self, temp_cache_db, monkeypatch):
        cache = MarketCache(str(temp_cache_db))
        cached_value = {"price": 99.0, "iv": 18.0, "hv252": 16.0}
        cache.set("md_AAPL", cached_value, ttl_seconds=-1)

        monkeypatch.setattr(get_market_data, "is_market_open", lambda: False)

        symbol, data = get_market_data.process_single_symbol("AAPL", cache_instance=cache)

        assert symbol == "AAPL"
        assert data["price"] == 99.0
        assert data["warning"] == "after_hours_stale"

    def test_process_single_symbol_futures_path(self, temp_cache_db, monkeypatch):
        cache = MarketCache(str(temp_cache_db))

        monkeypatch.setattr(get_market_data, "get_price", lambda *_args, **_kwargs: (100.0, False))
        monkeypatch.setattr(
            get_market_data,
            "calculate_hv",
            lambda *_args, **_kwargs: {
                "hv252": 10.0,
                "hv20": 5.0,
                "raw_returns": [0.01] * 60,
            },
        )
        monkeypatch.setattr(
            get_market_data, "get_current_iv", lambda *_args, **_kwargs: {"iv": 20.0}
        )
        monkeypatch.setattr(get_market_data, "safe_get_sector", lambda *_args, **_kwargs: "Energy")
        monkeypatch.setattr(
            get_market_data, "get_earnings_date", lambda *_args, **_kwargs: "2025-01-01"
        )

        symbol, data = get_market_data.process_single_symbol(
            "/CL",
            cache_instance=cache,
            ticker_factory=lambda _s: Mock(),
            market_open_fn=lambda: True,
        )

        assert symbol == "/CL"
        assert data["proxy"] is not None
        assert data["vrp_structural"] == 2.0
        assert data["vrp_tactical"] == 4.0

    def test_process_single_symbol_allows_after_hours_fetch(self, temp_cache_db, monkeypatch):
        cache = MarketCache(str(temp_cache_db))

        monkeypatch.setattr(get_market_data, "get_price", lambda *_args, **_kwargs: (120.0, False))
        monkeypatch.setattr(
            get_market_data,
            "calculate_hv",
            lambda *_args, **_kwargs: {
                "hv252": 12.0,
                "hv20": 6.0,
                "raw_returns": [0.01] * 60,
            },
        )
        monkeypatch.setattr(
            get_market_data, "get_current_iv", lambda *_args, **_kwargs: {"iv": 24.0}
        )
        monkeypatch.setattr(get_market_data, "safe_get_sector", lambda *_args, **_kwargs: "Tech")
        monkeypatch.setattr(get_market_data, "get_earnings_date", lambda *_args, **_kwargs: None)

        symbol, data = get_market_data.process_single_symbol(
            "AAPL",
            cache_instance=cache,
            allow_after_hours_fetch=True,
            ticker_factory=lambda _s: Mock(),
            market_open_fn=lambda: False,
        )

        assert symbol == "AAPL"
        assert data["price"] == 120.0
        assert data["is_stale"] is True

    def test_process_single_symbol_skips_symbol(self, temp_cache_db, monkeypatch):
        cache = MarketCache(str(temp_cache_db))
        monkeypatch.setattr(get_market_data, "SKIP_SYMBOLS", {"AAPL"})

        symbol, data = get_market_data.process_single_symbol("AAPL", cache_instance=cache)

        assert symbol == "AAPL"
        assert data["error"] == "skipped_symbol"

    def test_process_single_symbol_invalid_symbol_dict(self, temp_cache_db):
        cache = MarketCache(str(temp_cache_db))

        symbol, data = get_market_data.process_single_symbol(
            {"symbol": "AAPL"}, cache_instance=cache
        )

        assert symbol == "AAPL"
        assert "Invalid symbol type" in data["error"]

    def test_market_closed_no_cache_returns_error(self, temp_cache_db, monkeypatch):
        cache = MarketCache(str(temp_cache_db))
        monkeypatch.setattr(get_market_data, "is_market_open", lambda: False)

        symbol, data = get_market_data.process_single_symbol("AAPL", cache_instance=cache)

        assert symbol == "AAPL"
        assert data["error"] == "market_closed_no_cache"
        assert data["warning"] == "market_closed_no_cache"
        assert "Market closed" in data["warning_message"]

    def test_yfinance_failure_without_cache_returns_error(self, temp_cache_db, monkeypatch):
        cache = MarketCache(str(temp_cache_db))
        monkeypatch.setattr(get_market_data, "is_market_open", lambda: True)
        monkeypatch.setattr(get_market_data, "get_price", lambda *_args, **_kwargs: None)

        symbol, data = get_market_data.process_single_symbol("AAPL", cache_instance=cache)

        assert symbol == "AAPL"
        assert data["error"] == "price_unavailable"
        assert data["warning"] == "yfinance_unavailable_no_cache"


# ============================================================================
# TEST CLASS 4: Tastytrade merge preference
# ============================================================================


class TestTastytradeMerge:
    """Ensure Tastytrade earnings date is preferred over yfinance."""

    def test_merge_prefers_tastytrade_earnings_date(self):
        provider = get_market_data.TastytradeProvider(
            cache_instance=MarketCache(":memory:"),
            yf_fallback=get_market_data.YFinanceProvider(),
        )
        tt_data = {
            "symbol": "AAPL",
            "iv": 25.0,
            "hv30": 20.0,
            "hv90": 18.0,
            "earnings_date": "2025-02-01",
        }
        yf_data = {
            "price": 150.0,
            "iv": 22.0,
            "hv252": 19.0,
            "hv20": 16.0,
            "returns": [],
            "vrp_structural": 1.1,
            "vrp_tactical": 1.2,
            "earnings_date": "2025-01-10",
        }

        merged = provider._merge_tastytrade_yfinance("AAPL", tt_data, yf_data)
        assert merged["earnings_date"] == "2025-02-01"

    def test_merge_returns_yfinance_error(self):
        provider = get_market_data.TastytradeProvider(
            cache_instance=MarketCache(":memory:"),
            yf_fallback=get_market_data.YFinanceProvider(),
        )
        tt_data = {"symbol": "AAPL", "iv": 25.0}
        yf_data = {"error": "price_unavailable"}

        merged = provider._merge_tastytrade_yfinance("AAPL", tt_data, yf_data)

        assert merged["error"] == "price_unavailable"

    def test_compute_vrp_fallbacks(self):
        provider = get_market_data.TastytradeProvider(
            cache_instance=MarketCache(":memory:"),
            yf_fallback=get_market_data.YFinanceProvider(),
        )
        merged = {"iv": 20.0}
        tt_data = {"hv90": None, "hv30": None}
        yf_data = {"hv252": 10.0, "hv20": 5.0}

        updated = provider._compute_vrp(merged, tt_data, yf_data)

        assert updated["vrp_structural"] == 2.0
        assert updated["vrp_tactical"] == 4.0

    def test_merge_marks_yfinance_source_when_no_tt_data(self):
        provider = get_market_data.TastytradeProvider(
            cache_instance=MarketCache(":memory:"),
            yf_fallback=get_market_data.YFinanceProvider(),
        )
        merged = provider._merge_tastytrade_yfinance("AAPL", None, {"price": 150.0, "iv": 20.0})

        assert merged["data_source"] == "yfinance"

    def test_merge_clears_iv_warning_when_tastytrade_iv_present(self):
        provider = get_market_data.TastytradeProvider(
            cache_instance=MarketCache(":memory:"),
            yf_fallback=get_market_data.YFinanceProvider(),
        )
        tt_data = {"iv": 30.0, "hv30": 20.0, "hv90": 18.0}
        yf_data = {"price": 150.0, "iv": None, "warning": "iv_unavailable"}

        merged = provider._merge_tastytrade_yfinance("AAPL", tt_data, yf_data)

        assert merged["iv"] == 30.0
        assert merged["warning"] is None


class TestMarketDataHelpers:
    def test_map_symbol_prefers_direct_and_root_map(self, monkeypatch):
        monkeypatch.setattr(get_market_data, "SYMBOL_MAP", {"AAPL": "AAPLX", "/CL": "CL=F"})

        assert get_market_data.map_symbol("AAPL") == "AAPLX"
        assert get_market_data.map_symbol("/CLZ24") == "CL=F"
        assert get_market_data.map_symbol("") is None

    def test_is_etf_handles_invalid_input(self, monkeypatch):
        monkeypatch.setattr(get_market_data, "ETF_SYMBOLS", {"SPY"})

        assert get_market_data.is_etf({"bad": "input"}) is False
        assert get_market_data.is_etf("SPY") is True

    def test_should_skip_earnings_defensive(self, monkeypatch):
        monkeypatch.setattr(get_market_data, "SKIP_EARNINGS", {"AAPL"})

        assert get_market_data.should_skip_earnings({"bad": "input"}, "AAPL") is True
        assert get_market_data.should_skip_earnings("AAPL", {"bad": "input"}) is True
        assert get_market_data.should_skip_earnings("/CL", "CL=F") is True
        assert get_market_data.should_skip_earnings("AAPL", "AAPL") is True

    def test_get_earnings_date_uses_calendar_and_cache(self, temp_cache_db):
        cache = MarketCache(str(temp_cache_db))
        cal = pd.DataFrame([[pd.Timestamp("2025-01-02")]], index=["Earnings Date"])
        ticker = Mock()
        ticker.calendar = cal

        result = get_market_data.get_earnings_date(ticker, "AAPL", "AAPL", cache=cache)

        assert result == "2025-01-02"

        ticker.calendar = pd.DataFrame()
        result_cached = get_market_data.get_earnings_date(ticker, "AAPL", "AAPL", cache=cache)

        assert result_cached == "2025-01-02"

    def test_get_earnings_date_skips_when_configured(self, temp_cache_db):
        cache = MarketCache(str(temp_cache_db))
        ticker = Mock()
        ticker.calendar = pd.DataFrame([[pd.Timestamp("2025-01-02")]], index=["Earnings Date"])

        result = get_market_data.get_earnings_date(ticker, "/CL", "CL=F", cache=cache)

        assert result is None

    def test_safe_get_sector_respects_overrides_and_skip_api(self, temp_cache_db, monkeypatch):
        cache = MarketCache(str(temp_cache_db))
        monkeypatch.setattr(get_market_data, "SECTOR_OVERRIDES", {"AAPL": "Custom"})

        ticker = Mock()
        ticker.info = {"sector": "Technology"}

        assert get_market_data.safe_get_sector(ticker, "AAPL", "AAPL", cache=cache) == "Custom"
        assert (
            get_market_data.safe_get_sector(ticker, "MSFT", "MSFT", skip_api=True, cache=cache)
            == "Unknown"
        )

    def test_safe_get_sector_fetches_and_handles_errors(self, temp_cache_db):
        cache = MarketCache(str(temp_cache_db))
        ticker = Mock()
        ticker.info = {"sector": "Energy"}

        result = get_market_data.safe_get_sector(ticker, "XOM", "XOM", cache=cache)

        assert result == "Energy"

        broken = Mock()
        broken.info = Mock()
        broken.info.get.side_effect = RuntimeError("boom")

        assert get_market_data.safe_get_sector(broken, "BAD", "BAD", cache=cache) == "Unknown"


class TestProviderFallbacks:
    def test_tastytrade_provider_fallbacks_when_client_missing(self):
        class DummyProvider:
            def __init__(self, data):
                self.data = data

            def get_market_data(self, symbols):
                return {s: dict(self.data) for s in symbols}

        provider = get_market_data.TastytradeProvider(
            cache_instance=MarketCache(":memory:"),
            yf_fallback=DummyProvider({"price": 101.0}),
        )
        provider.tt_client = None

        results = provider.get_market_data(["AAPL"])

        assert results["AAPL"]["warning"] == "tastytrade_fallback"
        assert results["AAPL"]["data_source"] == "yfinance"

    def test_tastytrade_provider_fallbacks_on_auth_error(self):
        class DummyProvider:
            def __init__(self, data):
                self.data = data

            def get_market_data(self, symbols):
                return {s: dict(self.data) for s in symbols}

        provider = get_market_data.TastytradeProvider(
            cache_instance=MarketCache(":memory:"),
            yf_fallback=DummyProvider({"price": 101.0}),
        )
        provider.tt_client = Mock()
        provider.tt_client.get_market_metrics.side_effect = get_market_data.TastytradeAuthError(
            "auth"
        )

        results = provider.get_market_data(["AAPL"])

        assert results["AAPL"]["warning"] == "tastytrade_fallback"
        assert results["AAPL"]["data_source"] == "yfinance"

    def test_yfinance_provider_marks_stale_when_market_closed(self, monkeypatch):
        def fake_process(symbol, *_args, **_kwargs):
            return symbol, {"price": 100.0, "is_stale": False}

        monkeypatch.setattr(get_market_data, "process_single_symbol", fake_process)

        provider = get_market_data.YFinanceProvider(market_open_fn=lambda: False)
        results = provider.get_market_data(["AAPL"])

        assert results["AAPL"]["is_stale"] is True
        assert results["AAPL"]["data_source"] == "yfinance"
