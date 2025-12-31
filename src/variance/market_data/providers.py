import contextlib
import io
import math
from collections.abc import MutableMapping
from concurrent import futures
from datetime import datetime
from typing import Any, Optional, cast

import numpy as np

from ..interfaces import IMarketDataProvider, MarketData
from ..market_data import settings as md_settings
from ..market_data.cache import MarketCache, cache
from ..market_data.clock import is_market_open
from ..market_data.helpers import (
    _apply_provider_fallback,
    _fallback_to_cached_market_data,
    _get_cached_market_data,
    _log_provider_fallback,
    apply_warning,
    get_dynamic_ttl,
    make_cache_key,
)
from ..market_data.utils import is_etf, map_symbol, should_skip_earnings
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
        allow_after_hours_fetch = self.allow_after_hours_fetch and market_is_open

        with futures.ThreadPoolExecutor(max_workers=5) as executor:
            future_to_symbol = {
                executor.submit(
                    self._process_single_symbol,
                    s,
                    allow_after_hours_fetch,
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

    def _process_single_symbol(
        self,
        raw_symbol: str,
        allow_after_hours_fetch: bool = False,
    ) -> tuple[str, dict[str, Any]]:
        """
        Fetches and processes all metrics for a single ticker.
        Implements 'Bifurcated Proxy' logic for futures.
        """
        local_cache = self.cache
        market_is_open = self.market_open_fn()

        # Defensive: Handle case where raw_symbol might be a dict (shouldn't happen)
        if isinstance(raw_symbol, dict):
            symbol_str = str(raw_symbol.get("symbol", "UNKNOWN"))
            return symbol_str, {
                "error": f"Invalid symbol type: dict with keys {list(raw_symbol.keys())}"
            }

        if raw_symbol in md_settings.SKIP_SYMBOLS:
            return raw_symbol, {"error": "skipped_symbol"}

        cache_key = make_cache_key("market_data", raw_symbol)

        # Try fresh cache first (not expired)
        cached_all = _get_cached_market_data(local_cache, raw_symbol, allow_expired=False)

        if cached_all:
            return raw_symbol, cached_all

        # Market closed: Use stale cache or fail gracefully (avoid rate limits)
        if not market_is_open and not allow_after_hours_fetch:
            cached_stale = _get_cached_market_data(local_cache, raw_symbol, allow_expired=True)

            if cached_stale:
                # Mark as stale but usable
                apply_warning(
                    cached_stale,
                    "after_hours_stale",
                    provider="yfinance",
                    reason="market_closed",
                    cached=True,
                )
                return raw_symbol, cached_stale

            # No cache available and market closed - don't hammer yfinance
            message = "Market closed and no cached data available. Try again during market hours."
            payload = {
                "error": "market_closed_no_cache",
                "warning": "market_closed_no_cache",
            }
            apply_warning(
                payload,
                "market_closed_no_cache",
                message=message,
                provider="yfinance",
                reason="market_closed",
                cached=False,
            )
            return raw_symbol, payload

        # Market is open - proceed with fresh fetch
        try:
            # 1. Resolve Symbols
            # yf_symbol is the 'Cleanest' version of the root (e.g. CL=F)
            # proxy_symbol is the IV proxy (e.g. USO) for futures screening.
            yf_symbol = map_symbol(raw_symbol) or raw_symbol

            # For futures, prefer ETF proxy from FAMILY_MAP for clock-aligned math
            proxy_symbol = None
            if raw_symbol.startswith("/"):
                # Find ETF in same family
                for _family_name, members in md_settings.FAMILY_MAP.items():
                    if raw_symbol in members:
                        for member in members:
                            if not member.startswith("/") and not member.startswith("^"):
                                proxy_symbol = member
                                break
                        if proxy_symbol:
                            break

            # If no FAMILY_MAP proxy, fall back to FUTURES_PROXY
            if not proxy_symbol:
                proxy_config = md_settings.FUTURES_PROXY.get(raw_symbol)
                if isinstance(proxy_config, dict):
                    proxy_symbol = proxy_config.get("iv_symbol")
                elif isinstance(proxy_config, str):
                    proxy_symbol = proxy_config

            proxy_note = f"via {proxy_symbol}" if proxy_symbol else None
            is_futures = raw_symbol.startswith("/")

            if is_futures:
                futures_ticker = self.ticker_factory(yf_symbol)
                price_data = self._get_price(futures_ticker, yf_symbol)
                if not price_data:
                    # yfinance failed - try cache fallback even during "market hours"
                    cached_fallback = _fallback_to_cached_market_data(
                        local_cache,
                        raw_symbol,
                        warning="yfinance_unavailable_cached",
                        provider="yfinance",
                        reason="price_unavailable",
                    )
                    if cached_fallback:
                        return raw_symbol, cached_fallback
                    _log_provider_fallback(
                        "yfinance",
                        raw_symbol,
                        cached=False,
                        reason="price_unavailable",
                    )
                    payload = {
                        "error": "price_unavailable",
                        "warning": "yfinance_unavailable_no_cache",
                    }
                    apply_warning(
                        payload,
                        "yfinance_unavailable_no_cache",
                        provider="yfinance",
                        reason="price_unavailable",
                        cached=False,
                    )
                    return raw_symbol, payload

                hv_data = self._calculate_hv(futures_ticker, yf_symbol)
                if not hv_data:
                    # yfinance failed - try cache fallback
                    cached_fallback = _fallback_to_cached_market_data(
                        local_cache,
                        raw_symbol,
                        warning="yfinance_unavailable_cached",
                        provider="yfinance",
                        reason="history_unavailable",
                    )
                    if cached_fallback:
                        return raw_symbol, cached_fallback
                    _log_provider_fallback(
                        "yfinance",
                        raw_symbol,
                        cached=False,
                        reason="history_unavailable",
                    )
                    payload = {
                        "error": "history_unavailable",
                        "warning": "yfinance_unavailable_no_cache",
                    }
                    apply_warning(
                        payload,
                        "yfinance_unavailable_no_cache",
                        provider="yfinance",
                        reason="history_unavailable",
                        cached=False,
                    )
                    return raw_symbol, payload

                iv_data: dict[str, Any] = {}
                if proxy_symbol:
                    proxy_ticker = self.ticker_factory(proxy_symbol)
                    proxy_price = self._get_price(proxy_ticker, proxy_symbol)
                    if proxy_price:
                        iv_data = self._get_current_iv(
                            proxy_ticker,
                            proxy_price[0],
                            proxy_symbol,
                            hv_data.get("hv20"),
                        )

                if not iv_data:
                    iv_data = self._get_current_iv(
                        futures_ticker,
                        price_data[0],
                        yf_symbol,
                        hv_data.get("hv20"),
                    )

                if not iv_data:
                    iv_data = {"iv": None, "warning": "iv_unavailable"}
                    apply_warning(iv_data, "iv_unavailable", reason="options_unavailable")

                sector = self._safe_get_sector(
                    futures_ticker,
                    raw_symbol,
                    yf_symbol,
                    skip_api=True,
                )
                earnings_date = self._get_earnings_date(futures_ticker, raw_symbol, yf_symbol)
            else:
                math_symbol = proxy_symbol if proxy_symbol else yf_symbol
                math_ticker = self.ticker_factory(math_symbol)

                price_data = self._get_price(math_ticker, math_symbol)
                if not price_data:
                    # yfinance failed - try cache fallback even during "market hours"
                    cached_fallback = _fallback_to_cached_market_data(
                        local_cache,
                        raw_symbol,
                        warning="yfinance_unavailable_cached",
                        provider="yfinance",
                        reason="price_unavailable",
                    )
                    if cached_fallback:
                        return raw_symbol, cached_fallback
                    _log_provider_fallback(
                        "yfinance",
                        raw_symbol,
                        cached=False,
                        reason="price_unavailable",
                    )
                    payload = {
                        "error": "price_unavailable",
                        "warning": "yfinance_unavailable_no_cache",
                    }
                    apply_warning(
                        payload,
                        "yfinance_unavailable_no_cache",
                        provider="yfinance",
                        reason="price_unavailable",
                        cached=False,
                    )
                    return raw_symbol, payload

                hv_data = self._calculate_hv(math_ticker, math_symbol)
                if not hv_data:
                    # yfinance failed - try cache fallback
                    cached_fallback = _fallback_to_cached_market_data(
                        local_cache,
                        raw_symbol,
                        warning="yfinance_unavailable_cached",
                        provider="yfinance",
                        reason="history_unavailable",
                    )
                    if cached_fallback:
                        return raw_symbol, cached_fallback
                    _log_provider_fallback(
                        "yfinance",
                        raw_symbol,
                        cached=False,
                        reason="history_unavailable",
                    )
                    payload = {
                        "error": "history_unavailable",
                        "warning": "yfinance_unavailable_no_cache",
                    }
                    apply_warning(
                        payload,
                        "yfinance_unavailable_no_cache",
                        provider="yfinance",
                        reason="history_unavailable",
                        cached=False,
                    )
                    return raw_symbol, payload

                iv_data = self._get_current_iv(
                    math_ticker,
                    price_data[0],
                    math_symbol,
                    hv_data.get("hv20"),
                )
                if not iv_data:
                    iv_data = {"iv": None, "warning": "iv_unavailable"}
                    apply_warning(iv_data, "iv_unavailable", reason="options_unavailable")

                sector = self._safe_get_sector(
                    math_ticker,
                    raw_symbol,
                    math_symbol,
                    skip_api=is_etf(math_symbol),
                )
                earnings_date = self._get_earnings_date(math_ticker, raw_symbol, math_symbol)

            # Combine and Cache
            iv = iv_data.get("iv")
            hv252 = hv_data.get("hv252")

            res = {
                "price": price_data[0],
                "is_stale": price_data[1] or not market_is_open,
                "iv": iv,
                "hv252": hv252,
                "hv20": hv_data.get("hv20"),
                "returns": list(hv_data.get("raw_returns", [])[-60:]),
                "vrp_structural": iv / hv252 if (hv252 and iv is not None) else None,
                "vrp_tactical": (
                    iv / max(hv_data.get("hv20", 5.0), md_settings.HV_FLOOR_PERCENT)
                    if (hv_data.get("hv20") and iv is not None)
                    else None
                ),
                "sector": sector,
                "earnings_date": earnings_date,
                "proxy": proxy_note,
            }
            res.update(iv_data)

            # Override staleness if market is closed
            if not market_is_open:
                res["is_stale"] = True

            # Set data_source for yfinance-only processing
            res["data_source"] = "yfinance"

            local_cache.set(cache_key, res, get_dynamic_ttl("price", 600))
            return raw_symbol, res
        except Exception as e:
            import traceback

            error_trace = traceback.format_exc()
            return raw_symbol, {"error": str(e), "trace": error_trace[:500]}

    def _normalize_iv(
        self, iv_raw: float, hv_context: Optional[float] = None
    ) -> tuple[float, Optional[str]]:
        if iv_raw is None or iv_raw <= 0:
            return 0.0, "iv_zero_or_none"
        if hv_context and hv_context > 0:
            dist_raw = abs(math.log(iv_raw / hv_context))
            dist_scaled = abs(math.log((iv_raw * 100) / hv_context))
            if dist_scaled < dist_raw:
                return iv_raw * 100, "iv_scale_corrected"
            return iv_raw, None
        if iv_raw < 1.5:
            return iv_raw * 100, "iv_scale_assumed_decimal"
        return iv_raw, None

    def _get_price(self, ticker_obj: Any, yf_symbol: str) -> Optional[tuple[float, bool]]:
        cache_key = make_cache_key("price", yf_symbol)
        cached = self.cache.get(cache_key)
        if cached is not None:
            try:
                return float(cached), True
            except (TypeError, ValueError):
                pass

        try:
            # Use getattr to be safe with Mocks and different yfinance versions
            fast_info = getattr(ticker_obj, "fast_info", None)
            price = getattr(fast_info, "last_price", None)

            if price is not None:
                # Recursively drill down if we got a list/sequence
                while hasattr(price, "__len__") and not isinstance(price, (str, bytes, dict)):
                    if len(price) > 0:
                        price = price[0]
                    else:
                        return None

                price = float(price)
                if price > 0:
                    self.cache.set(cache_key, price, get_dynamic_ttl("price", 600))
                    return price, False
        except Exception:
            pass
        return None

    def _calculate_hv(self, ticker_obj: Any, yf_symbol: str) -> Optional[dict[str, Any]]:
        cache_key = make_cache_key("hv", yf_symbol)
        cached = self.cache.get(cache_key)
        if cached:
            return cast(dict[str, Any], cached)
        try:
            hist = ticker_obj.history(period="2y")
            if len(hist) < md_settings.HV_MIN_HISTORY_DAYS:
                return None
            returns = np.log(hist["Close"] / hist["Close"].shift(1)).dropna()

            def _vol(window: int) -> float:
                return float(returns.tail(window).std() * np.sqrt(252) * 100)

            res = {
                "hv252": _vol(252),
                "hv60": _vol(60),
                "hv20": _vol(20),
                "hv20_stderr": float(returns.tail(20).std() / np.sqrt(20) * np.sqrt(252) * 100),
                "raw_returns": returns.tolist(),
            }

            # Calculate HV Rank (Heuristic: where current hv20 sits vs last 252 days)
            try:
                rolling_vol = returns.rolling(window=20).std() * np.sqrt(252) * 100
                rolling_vol = rolling_vol.dropna()
                if len(rolling_vol) > 20:
                    current_vol = res["hv20"]
                    rank = (rolling_vol < current_vol).sum() / len(rolling_vol) * 100.0
                    res["hv_rank"] = float(rank)
            except Exception:
                pass

            self.cache.set(cache_key, res, get_dynamic_ttl("hv", 86400))
            return res
        except Exception:
            return None

    def _get_current_iv(
        self,
        ticker_obj: Any,
        price: float,
        yf_symbol: str,
        hv_context: Optional[float] = None,
    ) -> dict[str, Any]:
        cache_key = make_cache_key("iv", yf_symbol)
        cached = self.cache.get(cache_key)
        if cached:
            return cast(dict[str, Any], cached)
        try:
            options = ticker_obj.options
            if not options:
                return {}
            target_date = None
            now = datetime.now()
            for opt_date in options:
                dte = (datetime.strptime(opt_date, "%Y-%m-%d") - now).days
                if md_settings.DTE_MIN <= dte <= md_settings.DTE_MAX:
                    target_date = opt_date
                    break
            if not target_date:
                target_date = options[0]
            chain = ticker_obj.option_chain(target_date)
            calls, puts = chain.calls, chain.puts
            if calls.empty or puts.empty:
                return {}

            # AFTER-HOURS CHECK: If bid/asks are zero, the live data is "Bad"
            is_zero_bid = (calls["bid"].sum() == 0 and calls["ask"].sum() == 0) or (
                puts["bid"].sum() == 0 and puts["ask"].sum() == 0
            )

            if is_zero_bid:
                return {}

            calls["dist"] = abs(calls["strike"] - price)
            puts["dist"] = abs(puts["strike"] - price)
            atm_call = calls.sort_values("dist").iloc[0]
            atm_put = puts.sort_values("dist").iloc[0]
            raw_iv = (atm_call["impliedVolatility"] + atm_put["impliedVolatility"]) / 2
            iv, warning = self._normalize_iv(raw_iv, hv_context)

            def _safe_float(value: Any, default: float = 0.0) -> float:
                try:
                    if value is None:
                        return default
                    val = float(value)
                    if math.isnan(val):
                        return default
                    return val
                except (TypeError, ValueError):
                    return default

            atm_vol = int(_safe_float(atm_call.get("volume")) + _safe_float(atm_put.get("volume")))
            atm_oi = int(
                _safe_float(atm_call.get("openInterest")) + _safe_float(atm_put.get("openInterest"))
            )
            res = {
                "iv": iv,
                "warning": warning,
                "atm_volume": atm_vol,
                "atm_vol": atm_vol,
                "atm_oi": atm_oi,
                "atm_bid": float((atm_call["bid"] + atm_put["bid"]) / 2),
                "atm_ask": float((atm_call["ask"] + atm_put["ask"]) / 2),
                "call_bid": float(atm_call["bid"]),
                "call_ask": float(atm_call["ask"]),
                "put_bid": float(atm_put["bid"]),
                "put_ask": float(atm_put["ask"]),
            }
            if warning:
                apply_warning(res, warning, reason="iv_normalization")
            self.cache.set(cache_key, res, get_dynamic_ttl("iv", 900))
            return res
        except Exception:
            return {}

    def _get_earnings_date(self, ticker_obj: Any, raw_symbol: str, yf_symbol: str) -> Optional[str]:
        cache_key = make_cache_key("earn", yf_symbol)
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cast(Optional[str], cached)
        if should_skip_earnings(raw_symbol, yf_symbol):
            return None
        try:
            cal = ticker_obj.calendar
            if cal is not None and not cal.empty and "Earnings Date" in cal.index:
                ed = cal.loc["Earnings Date"][0]
                if hasattr(ed, "to_pydatetime"):
                    ed = ed.to_pydatetime()
                val = str(ed.strftime("%Y-%m-%d"))
                self.cache.set(cache_key, val, get_dynamic_ttl("earnings", 604800))
                return val
        except Exception:
            pass
        return None

    def _safe_get_sector(
        self,
        ticker_obj: Any,
        raw_symbol: str,
        yf_symbol: str,
        skip_api: bool = False,
    ) -> str:
        if raw_symbol in md_settings.SECTOR_OVERRIDES:
            return str(md_settings.SECTOR_OVERRIDES[raw_symbol])
        cache_key = make_cache_key("sec", yf_symbol)
        cached = self.cache.get(cache_key)
        if cached:
            return str(cached)
        if skip_api:
            return "Unknown"
        try:
            with contextlib.redirect_stderr(io.StringIO()):
                sec = ticker_obj.info.get("sector", "Unknown")
            self.cache.set(cache_key, sec, get_dynamic_ttl("sector", 2592000))
            return str(sec)
        except Exception:
            return "Unknown"


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
        self.market_open_fn = market_open_fn or is_market_open
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

    def _is_market_open(self) -> bool:
        try:
            return bool(self.market_open_fn())
        except Exception:
            return True

    def get_market_data(self, symbols: list[str]) -> dict[str, MarketData]:
        # NOTE: Tastytrade API works after hours! Only skip if client is unavailable
        # After hours: fresh Tastytrade metrics + cached yfinance price = valid composite

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
            merged = self._merge_tastytrade_yfinance(sym, tt_metrics.get(sym), yf_results.get(sym))
            final_results[sym] = merged

            # Cache the merged Tastytrade+yfinance result
            # This ensures we don't lose Tastytrade metrics on yfinance rate limit fallback
            if "error" not in merged:
                from ..market_data.helpers import get_dynamic_ttl, make_cache_key

                cache_key = make_cache_key("market_data", sym)
                self.cache.set(cache_key, merged, get_dynamic_ttl("iv", 900))

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
        iv = merged_data.get("iv")
        if iv is None or iv <= 0:
            return merged_data

        hv90 = tt_data.get("hv90")
        # YF Fallback: Prefer synthetic HV90 over HV252 to match regime
        yf_hv90 = yf_data.get("hv90") if yf_data else None
        yf_hv252 = yf_data.get("hv252") if yf_data else None
        hv_floor = md_settings.HV_FLOOR_PERCENT

        if hv90 is not None and hv90 > 0:
            merged_data["vrp_structural"] = iv / max(hv90, hv_floor)
        elif yf_hv90 is not None and yf_hv90 > 0:
            merged_data["vrp_structural"] = iv / max(yf_hv90, hv_floor)
        elif yf_hv252 is not None and yf_hv252 > 0:
            merged_data["vrp_structural"] = iv / max(yf_hv252, hv_floor)

        hv30 = tt_data.get("hv30")
        hv20 = yf_data.get("hv20") if yf_data else None

        if hv30 is not None:
            merged_data["vrp_tactical"] = iv / max(hv30, hv_floor)
        elif hv20 is not None:
            merged_data["vrp_tactical"] = iv / max(hv20, hv_floor)

        return merged_data


__all__ = ["YFinanceProvider", "TastytradeProvider"]
