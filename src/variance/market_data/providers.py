from collections.abc import MutableMapping
from concurrent import futures
from typing import Any, Optional, cast

from ..get_market_data import process_single_symbol
from ..interfaces import IMarketDataProvider, MarketData
from ..market_data.cache import MarketCache, cache
from ..market_data.clock import is_market_open
from ..market_data.helpers import _apply_provider_fallback
from ..tastytrade_client import TastytradeAuthError, TastytradeClient, TastytradeMetrics

try:
    import yfinance as yf
except ModuleNotFoundError as exc:
    raise ModuleNotFoundError("Missing dependency 'yfinance'. Activate your venv.") from exc


TickerFactory = Any
MarketOpenFn = Any


class YFinanceProvider(IMarketDataProvider):
    def __init__(
        self,
        cache_instance: Optional[MarketCache] = None,
        allow_after_hours_fetch: bool = False,
        ticker_factory: Optional[TickerFactory] = None,
        market_open_fn: Optional[MarketOpenFn] = None,
    ):
        self.cache = cache_instance if cache_instance else cache
        self.allow_after_hours_fetch = allow_after_hours_fetch
        self.ticker_factory = ticker_factory or yf.Ticker
        self.market_open_fn = market_open_fn or is_market_open

    def get_market_data(self, symbols: list[str]) -> dict[str, MarketData]:
        unique_symbols = list(set(symbols))
        results: dict[str, MarketData] = {}

        market_is_open = self.market_open_fn()

        with futures.ThreadPoolExecutor(max_workers=5) as executor:
            future_to_symbol = {
                executor.submit(
                    process_single_symbol,
                    s,
                    self.cache,
                    self.allow_after_hours_fetch,
                    self.ticker_factory,
                    self.market_open_fn,
                ): s
                for s in unique_symbols
            }
            for future in futures.as_completed(future_to_symbol):
                try:
                    sym, data = future.result()

                    if not market_is_open and "error" not in data:
                        data["is_stale"] = True
                        data["data_source"] = "yfinance"

                    results[sym] = cast(MarketData, data)
                except Exception as e:
                    results[future_to_symbol[future]] = cast(MarketData, {"error": str(e)})
        return results


class TastytradeProvider(IMarketDataProvider):
    """
    Composite market data provider using Tastytrade for volatility metrics
    and yfinance for price/returns data.
    """

    def __init__(
        self,
        cache_instance: Optional[MarketCache] = None,
        yf_fallback: Optional[YFinanceProvider] = None,
        allow_after_hours_fetch: bool = False,
        ticker_factory: Optional[TickerFactory] = None,
        market_open_fn: Optional[MarketOpenFn] = None,
    ):
        self.cache = cache_instance if cache_instance else cache
        self.yf_provider = (
            yf_fallback
            if yf_fallback
            else YFinanceProvider(
                cache_instance,
                allow_after_hours_fetch=allow_after_hours_fetch,
                ticker_factory=ticker_factory,
                market_open_fn=market_open_fn,
            )
        )

        self.tt_client: Optional[TastytradeClient]
        try:
            self.tt_client = TastytradeClient()
        except TastytradeAuthError:
            self.tt_client = None

    def get_market_data(self, symbols: list[str]) -> dict[str, MarketData]:
        if self.tt_client is None:
            results = self.yf_provider.get_market_data(symbols)
            for sym in results:
                if "error" not in results[sym]:
                    _apply_provider_fallback(
                        cast(MutableMapping[str, Any], results[sym]),
                        symbol=sym,
                        warning="tastytrade_fallback",
                        provider="yfinance",
                        reason="client_unavailable",
                        cached=False,
                    )
            return results

        try:
            tt_metrics = self.tt_client.get_market_metrics(symbols)
        except TastytradeAuthError:
            results = self.yf_provider.get_market_data(symbols)
            for sym in results:
                if "error" not in results[sym]:
                    _apply_provider_fallback(
                        cast(MutableMapping[str, Any], results[sym]),
                        symbol=sym,
                        warning="tastytrade_fallback",
                        provider="yfinance",
                        reason="auth_error",
                        cached=False,
                    )
            return results
        except Exception:
            results = self.yf_provider.get_market_data(symbols)
            for sym in results:
                if "error" not in results[sym]:
                    _apply_provider_fallback(
                        cast(MutableMapping[str, Any], results[sym]),
                        symbol=sym,
                        warning="tastytrade_fallback",
                        provider="yfinance",
                        reason="exception",
                        cached=False,
                    )
            return results

        yf_results = self.yf_provider.get_market_data(symbols)

        final_results: dict[str, MarketData] = {}
        for sym in symbols:
            final_results[sym] = self._merge_tastytrade_yfinance(
                sym, tt_metrics.get(sym), yf_results.get(sym)
            )

        return final_results

    def _merge_tastytrade_yfinance(
        self,
        symbol: str,
        tt_data: Optional[TastytradeMetrics],
        yf_data: Optional[MarketData],
    ) -> MarketData:
        if not yf_data:
            return cast(MarketData, {"error": "yfinance_unavailable"})

        if "error" in yf_data:
            return yf_data

        merged = dict(yf_data)

        if tt_data:
            if "iv" in tt_data and tt_data["iv"] is not None:
                merged["iv"] = tt_data["iv"]
                if merged.get("warning") == "iv_unavailable":
                    merged["warning"] = None

            if "iv_rank" in tt_data and tt_data["iv_rank"] is not None:
                merged["iv_rank"] = tt_data["iv_rank"]

            if "iv_percentile" in tt_data and tt_data["iv_percentile"] is not None:
                merged["iv_percentile"] = tt_data["iv_percentile"]

            if "liquidity_rating" in tt_data and tt_data["liquidity_rating"] is not None:
                merged["liquidity_rating"] = tt_data["liquidity_rating"]

            if "liquidity_value" in tt_data and tt_data["liquidity_value"] is not None:
                merged["liquidity_value"] = tt_data["liquidity_value"]

            if "option_volume" in tt_data and tt_data["option_volume"] is not None:
                merged["option_volume"] = tt_data["option_volume"]
                merged["atm_volume"] = tt_data["option_volume"]

            if "corr_spy_3month" in tt_data and tt_data["corr_spy_3month"] is not None:
                merged["corr_spy_3month"] = tt_data["corr_spy_3month"]

            if "beta" in tt_data and tt_data["beta"] is not None:
                merged["beta"] = tt_data["beta"]

            if "hv30" in tt_data and tt_data["hv30"] is not None:
                merged["hv30"] = tt_data["hv30"]

            if "hv90" in tt_data and tt_data["hv90"] is not None:
                merged["hv90"] = tt_data["hv90"]

            if "hv_rank" in yf_data and yf_data["hv_rank"] is not None:
                merged["hv_rank"] = yf_data["hv_rank"]

            if "earnings_date" in tt_data and tt_data["earnings_date"] is not None:
                merged["earnings_date"] = tt_data["earnings_date"]

            merged = self._compute_vrp(merged, tt_data, yf_data)

            merged["data_source"] = "composite"
        else:
            merged["data_source"] = "yfinance"

        return cast(MarketData, merged)

    def _compute_vrp(
        self,
        merged_data: dict[str, Any],
        tt_data: TastytradeMetrics,
        yf_data: Optional[MarketData] = None,
    ) -> dict[str, Any]:
        from ..get_market_data import HV_FLOOR_PERCENT

        iv = merged_data.get("iv")
        if iv is None or iv <= 0:
            return merged_data

        hv90 = tt_data.get("hv90")
        hv252 = yf_data.get("hv252") if yf_data else None
        hv_floor = HV_FLOOR_PERCENT

        if hv90 is not None and hv90 > 0:
            merged_data["vrp_structural"] = iv / max(hv90, hv_floor)
        elif hv252 is not None and hv252 > 0:
            merged_data["vrp_structural"] = iv / max(hv252, hv_floor)

        hv30 = tt_data.get("hv30")
        hv20 = yf_data.get("hv20") if yf_data else None

        if hv30 is not None:
            merged_data["vrp_tactical"] = iv / max(hv30, hv_floor)
        elif hv20 is not None:
            merged_data["vrp_tactical"] = iv / max(hv20, hv_floor)

        return merged_data


__all__ = ["YFinanceProvider", "TastytradeProvider"]
