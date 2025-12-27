import contextlib
import io
import math
import sys
from datetime import datetime
from typing import Any, Callable, Optional, cast

import numpy as np

from .market_data import settings as md_settings
from .market_data.cache import MarketCache, cache
from .market_data.clock import is_market_open
from .market_data.helpers import (
    _fallback_to_cached_market_data,
    _get_cached_market_data,
    _log_provider_fallback,
    apply_warning,
    get_dynamic_ttl,
    make_cache_key,
)

# Import Variance Logger

try:
    import yfinance as yf
except ModuleNotFoundError:
    print("Error: Missing dependency 'yfinance'. Activate your venv.", file=sys.stderr)
    sys.exit(1)

# --- CONFIGURATION ---
DEFAULT_TTL = md_settings.DEFAULT_TTL
DB_PATH = md_settings.DB_PATH
TTL = md_settings.TTL
HV_MIN_HISTORY_DAYS = md_settings.HV_MIN_HISTORY_DAYS

SKIP_EARNINGS = md_settings.SKIP_EARNINGS
SKIP_SYMBOLS = md_settings.SKIP_SYMBOLS
SYMBOL_MAP = md_settings.SYMBOL_MAP
SECTOR_OVERRIDES = md_settings.SECTOR_OVERRIDES
ETF_SYMBOLS = md_settings.ETF_SYMBOLS
FUTURES_PROXY = md_settings.FUTURES_PROXY
FAMILY_MAP = md_settings.FAMILY_MAP
DATA_FETCHING = md_settings.DATA_FETCHING
DTE_MIN = md_settings.DTE_MIN
DTE_MAX = md_settings.DTE_MAX
TARGET_DTE = md_settings.TARGET_DTE
STRIKE_LOWER = md_settings.STRIKE_LOWER
STRIKE_UPPER = md_settings.STRIKE_UPPER
OPTION_CHAIN_LIMIT = md_settings.OPTION_CHAIN_LIMIT

try:
    from .config_loader import load_trading_rules

    HAS_TRADING_RULES = True
except ImportError:
    HAS_TRADING_RULES = False

HV_FLOOR_PERCENT = 5.0
if HAS_TRADING_RULES:
    try:
        from .config_loader import load_trading_rules

        _rules = load_trading_rules()
        HV_FLOOR_PERCENT = float(_rules.get("hv_floor_percent", HV_FLOOR_PERCENT))
    except Exception:
        pass


TickerFactory = Callable[[str], Any]
MarketOpenFn = Callable[[], bool]


def map_symbol(raw_symbol: str) -> Optional[str]:
    if not raw_symbol:
        return None
    if raw_symbol in SYMBOL_MAP:
        return SYMBOL_MAP[raw_symbol]  # type: ignore[no-any-return]
    if raw_symbol.startswith("/"):
        root = raw_symbol[1:3]
        if f"/{root}" in SYMBOL_MAP:
            return SYMBOL_MAP[f"/{root}"]  # type: ignore[no-any-return]
    return raw_symbol


def is_etf(symbol: str) -> bool:
    if isinstance(symbol, dict):
        return False  # Not an ETF if invalid input
    return symbol.upper() in ETF_SYMBOLS


def should_skip_earnings(raw_symbol: str, yf_symbol: str) -> bool:
    # Defensive: Handle case where parameters might be dicts
    if isinstance(raw_symbol, dict):
        return True  # Skip earnings for invalid input
    if isinstance(yf_symbol, dict):
        return True

    upper = raw_symbol.upper()
    if raw_symbol.startswith("/") or yf_symbol.endswith("=F") or yf_symbol.startswith("^"):
        return True
    return upper in SKIP_EARNINGS


def normalize_iv(iv_raw: float, hv_context: Optional[float] = None) -> tuple[float, Optional[str]]:
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


def get_price(
    ticker_obj: Any, yf_symbol: str, cache: Optional[MarketCache] = None
) -> Optional[tuple[float, bool]]:
    if cache is None:
        # Use getattr to allow monkeypatching in tests
        import sys

        local_cache = sys.modules[__name__].cache
    else:
        local_cache = cache
    cache_key = make_cache_key("price", yf_symbol)
    cached = local_cache.get(cache_key)
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
                local_cache.set(cache_key, price, get_dynamic_ttl("price", 600))
                return price, False
    except Exception:
        pass
    return None


def calculate_hv(
    ticker_obj: Any, yf_symbol: str, cache: Optional[MarketCache] = None
) -> Optional[dict[str, Any]]:
    if cache is None:
        # Use getattr to allow monkeypatching in tests
        import sys

        local_cache = sys.modules[__name__].cache
    else:
        local_cache = cache
    cache_key = make_cache_key("hv", yf_symbol)
    cached = local_cache.get(cache_key)
    if cached:
        return cast(dict[str, Any], cached)
    try:
        hist = ticker_obj.history(period="2y")
        if len(hist) < HV_MIN_HISTORY_DAYS:
            return None
        returns = np.log(hist["Close"] / hist["Close"].shift(1)).dropna()

        def _vol(window: int) -> float:
            return float(returns.tail(window).std() * np.sqrt(252) * 100)

        res = {
            "hv252": _vol(252),
            "hv60": _vol(60),
            "hv20": _vol(20),
            "hv20_stderr": float(returns.tail(20).std() / np.sqrt(20) * np.sqrt(252) * 100),
            "raw_returns": returns.tolist(),  # Store list for JSON serialization
        }

        # Calculate HV Rank (Heuristic: where current hv20 sits vs last 252 days)
        try:
            # Generate a rolling window of 20-day volatilities for the last year
            rolling_vol = returns.rolling(window=20).std() * np.sqrt(252) * 100
            rolling_vol = rolling_vol.dropna()
            if len(rolling_vol) > 20:
                current_vol = res["hv20"]
                # Count how many days were lower than today
                rank = (rolling_vol < current_vol).sum() / len(rolling_vol) * 100.0
                res["hv_rank"] = float(rank)
        except Exception:
            pass

        local_cache.set(cache_key, res, get_dynamic_ttl("hv", 86400))
        return res
    except Exception:
        return None


def get_current_iv(
    ticker_obj: Any,
    price: float,
    yf_symbol: str,
    hv_context: Optional[float] = None,
    cache: Optional[MarketCache] = None,
) -> dict[str, Any]:
    """
    Get current implied volatility from ATM options.

    Measurement Point: AT-THE-MONEY (closest strike to current price)

    Why ATM (not OTM)?
        - We trade: 20-30 delta strangles (OTM wings)
        - We measure: ATM IV (50-delta)

        This is NOT a mismatch because:
        1. ATM anchors the entire vol surface (all strikes priced relative to ATM)
        2. Skew cancels out for delta-neutral strategies
           Wing IV = (25d_put + 25d_call) / 2 ≈ ATM IV
        3. Tastylive/Spina methodology uses overall IV (not skew optimization)
        4. For stock screening (not strike optimization), ATM is the best proxy

        See ADR-0012 for mathematical proof of skew cancellation.

    Calculation:
        1. Find closest call strike to price (ATM call)
        2. Find closest put strike to price (ATM put)
        3. Average their implied volatilities: IV = (call_iv + put_iv) / 2

    DTE Selection:
        - Prefer options between 20-45 DTE (configurable via DTE_MIN/DTE_MAX)
        - If none available, use nearest expiration
        - This aligns with ~30-day IV convention

    Args:
        ticker_obj: yfinance Ticker object
        price: Current stock price
        yf_symbol: Yahoo Finance symbol (for caching)
        hv_context: Historical vol for normalization (optional)
        cache: Cache instance (optional, uses global if not provided)

    Returns:
        Dict with keys:
            - iv: Implied volatility (annualized %)
            - warning: Data quality warning (if any)
            - atm_volume: Combined ATM call + put volume
            - atm_oi: Combined ATM call + put open interest
            - atm_bid, atm_ask: Average of call/put bids/asks
            - call_bid, call_ask, put_bid, put_ask: Individual leg quotes
    """
    if cache is None:
        # Use getattr to allow monkeypatching in tests
        import sys

        local_cache = sys.modules[__name__].cache
    else:
        local_cache = cache
    cache_key = make_cache_key("iv", yf_symbol)
    cached = local_cache.get(cache_key)
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
            if DTE_MIN <= dte <= DTE_MAX:
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
        iv, warning = normalize_iv(raw_iv, hv_context)

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
        local_cache.set(cache_key, res, get_dynamic_ttl("iv", 900))
        return res
    except Exception:
        return {}


def get_earnings_date(
    ticker_obj: Any, raw_symbol: str, yf_symbol: str, cache: Optional[MarketCache] = None
) -> Optional[str]:
    if cache is None:
        # Use getattr to allow monkeypatching in tests
        import sys

        local_cache = sys.modules[__name__].cache
    else:
        local_cache = cache
    cache_key = make_cache_key("earn", yf_symbol)
    cached = local_cache.get(cache_key)
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
            local_cache.set(cache_key, val, get_dynamic_ttl("earnings", 604800))
            return val
    except Exception:
        pass
    return None


def safe_get_sector(
    ticker_obj: Any,
    raw_symbol: str,
    yf_symbol: str,
    skip_api: bool = False,
    cache: Optional[MarketCache] = None,
) -> str:
    if raw_symbol in SECTOR_OVERRIDES:
        return str(SECTOR_OVERRIDES[raw_symbol])
    if cache is None:
        # Use getattr to allow monkeypatching in tests
        import sys

        local_cache = sys.modules[__name__].cache
    else:
        local_cache = cache
    cache_key = make_cache_key("sec", yf_symbol)
    cached = local_cache.get(cache_key)
    if cached:
        return str(cached)
    if skip_api:
        return "Unknown"
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            sec = ticker_obj.info.get("sector", "Unknown")
        local_cache.set(cache_key, sec, get_dynamic_ttl("sector", 2592000))
        return str(sec)
    except Exception:
        return "Unknown"


def process_single_symbol(
    raw_symbol: str,
    cache_instance: Optional[MarketCache] = None,
    allow_after_hours_fetch: bool = False,
    ticker_factory: Optional[TickerFactory] = None,
    market_open_fn: Optional[MarketOpenFn] = None,
) -> tuple[str, dict[str, Any]]:
    """
    Fetches and processes all metrics for a single ticker.
    Implements 'Bifurcated Proxy' logic for futures.
    """
    if cache_instance is None:
        # Use getattr to allow monkeypatching in tests
        import sys

        local_cache = sys.modules[__name__].cache
    else:
        local_cache = cache_instance
    market_open_fn = market_open_fn or is_market_open
    ticker_factory = ticker_factory or yf.Ticker
    market_is_open = market_open_fn()

    # Defensive: Handle case where raw_symbol might be a dict (shouldn't happen)
    if isinstance(raw_symbol, dict):
        symbol_str = str(raw_symbol.get("symbol", "UNKNOWN"))
        return symbol_str, {
            "error": f"Invalid symbol type: dict with keys {list(raw_symbol.keys())}"
        }

    if raw_symbol in SKIP_SYMBOLS:
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
        else:
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
            for _family_name, members in FAMILY_MAP.items():
                if raw_symbol in members:
                    for member in members:
                        if not member.startswith("/") and not member.startswith("^"):
                            proxy_symbol = member
                            break
                    if proxy_symbol:
                        break

        # If no FAMILY_MAP proxy, fall back to FUTURES_PROXY
        if not proxy_symbol:
            proxy_config = FUTURES_PROXY.get(raw_symbol)
            if isinstance(proxy_config, dict):
                proxy_symbol = proxy_config.get("iv_symbol")
            elif isinstance(proxy_config, str):
                proxy_symbol = proxy_config

        proxy_note = f"via {proxy_symbol}" if proxy_symbol else None
        is_futures = raw_symbol.startswith("/")

        if is_futures:
            futures_ticker = ticker_factory(yf_symbol)
            price_data = get_price(futures_ticker, yf_symbol, cache=local_cache)
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

            hv_data = calculate_hv(futures_ticker, yf_symbol, cache=local_cache)
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

            iv_data = {}
            if proxy_symbol:
                proxy_ticker = ticker_factory(proxy_symbol)
                proxy_price = get_price(proxy_ticker, proxy_symbol, cache=local_cache)
                if proxy_price:
                    iv_data = get_current_iv(
                        proxy_ticker,
                        proxy_price[0],
                        proxy_symbol,
                        hv_data.get("hv20"),
                        cache=local_cache,
                    )

            if not iv_data:
                iv_data = get_current_iv(
                    futures_ticker,
                    price_data[0],
                    yf_symbol,
                    hv_data.get("hv20"),
                    cache=local_cache,
                )

            if not iv_data:
                iv_data = {"iv": None, "warning": "iv_unavailable"}
                apply_warning(iv_data, "iv_unavailable", reason="options_unavailable")

            sector = safe_get_sector(
                futures_ticker,
                raw_symbol,
                yf_symbol,
                skip_api=True,
                cache=local_cache,
            )
            earnings_date = get_earnings_date(
                futures_ticker, raw_symbol, yf_symbol, cache=local_cache
            )
        else:
            math_symbol = proxy_symbol if proxy_symbol else yf_symbol
            math_ticker = ticker_factory(math_symbol)

            price_data = get_price(math_ticker, math_symbol, cache=local_cache)
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

            hv_data = calculate_hv(math_ticker, math_symbol, cache=local_cache)
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

            iv_data = get_current_iv(
                math_ticker,
                price_data[0],
                math_symbol,
                hv_data.get("hv20"),
                cache=local_cache,
            )
            if not iv_data:
                iv_data = {"iv": None, "warning": "iv_unavailable"}
                apply_warning(iv_data, "iv_unavailable", reason="options_unavailable")

            sector = safe_get_sector(
                math_ticker,
                raw_symbol,
                math_symbol,
                skip_api=is_etf(math_symbol),
                cache=local_cache,
            )
            earnings_date = get_earnings_date(
                math_ticker, raw_symbol, math_symbol, cache=local_cache
            )

        # Combine and Cache
        iv = iv_data.get("iv")
        hv252 = hv_data.get("hv252")

        res = {
            "price": price_data[0],
            "is_stale": price_data[1] or not market_is_open,
            "iv": iv,
            "hv252": hv252,
            "hv20": hv_data.get("hv20"),
            "returns": list(hv_data.get("raw_returns", [])[-60:]),  # Last 60 days for correlation
            "vrp_structural": iv / hv252 if (hv252 and iv is not None) else None,
            "vrp_tactical": (
                iv / max(hv_data.get("hv20", 5.0), HV_FLOOR_PERCENT)
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


from typing import TYPE_CHECKING

from .interfaces import MarketData
from .tastytrade_client import TastytradeAuthError

__all__ = [
    "get_market_data",
    "MarketDataService",
    "MarketData",
    "YFinanceProvider",
    "TastytradeProvider",
    "MarketDataFactory",
    "_reset_default_service",
    "TastytradeAuthError",
    "is_market_open",
    "cache",
    "MarketCache",
]


if TYPE_CHECKING:
    from .market_data.providers import TastytradeProvider, YFinanceProvider
    from .market_data.service import MarketDataFactory, MarketDataService


def __getattr__(name: str) -> Any:
    if name in {"YFinanceProvider", "TastytradeProvider"}:
        from .market_data import providers

        return getattr(providers, name)
    if name in {"MarketDataService", "MarketDataFactory"}:
        from .market_data import service

        return getattr(service, name)
    if name in {"cache", "MarketCache"}:
        from .market_data.cache import MarketCache, cache

        return cache if name == "cache" else MarketCache
    if name == "TastytradeAuthError":
        from .tastytrade_client import TastytradeAuthError

        return TastytradeAuthError
    if name == "is_market_open":
        from .market_data.clock import is_market_open

        return is_market_open
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


def get_market_data(
    symbols: list[str], _service: Optional["MarketDataService"] = None
) -> dict[str, MarketData]:
    from .market_data.service import get_market_data as _get_market_data

    return _get_market_data(symbols, _service=_service)


def _reset_default_service() -> None:
    from .market_data.service import _reset_default_service as _reset

    _reset()
