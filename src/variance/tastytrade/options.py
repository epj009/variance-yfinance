"""
Option Chain Fetching for Tastytrade API.

This module provides:
- Option chain fetching (equity and futures)
- ATM option selection
- OCC symbol building
- Chain normalization and parsing
"""

import asyncio
import json
import logging
import time
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote

try:
    import httpx
except ModuleNotFoundError:
    raise ImportError("Missing dependency 'httpx'. Install with: pip install httpx") from None

from ..market_data.cache import MarketCache
from ..market_data.helpers import get_dynamic_ttl, make_cache_key
from .auth import TastytradeCredentials, TokenManager

logger = logging.getLogger(__name__)


class OptionChainFetcher:
    """
    Fetch option chain data from Tastytrade API.

    Handles:
    - Equity option chains (parallel async fetching)
    - Futures option chains
    - ATM option selection
    - OCC symbol building
    - Chain normalization (full vs compact endpoint)
    """

    def __init__(
        self, token_manager: TokenManager, credentials: TastytradeCredentials, cache: MarketCache
    ):
        """
        Initialize option chain fetcher.

        Args:
            token_manager: Token manager for authentication
            credentials: OAuth credentials
            cache: Market data cache instance
        """
        self._token_manager = token_manager
        self._credentials = credentials
        self._cache = cache

    async def _fetch_option_chain_async(
        self, symbol: str, semaphore: asyncio.Semaphore
    ) -> tuple[str, Optional[dict[str, Any]]]:
        """
        Fetch a single option chain asynchronously with rate limiting.

        Args:
            symbol: Underlying symbol (e.g., 'AAPL')
            semaphore: Semaphore for rate limiting

        Returns:
            Tuple of (symbol, normalized_chain_data)
        """
        async with semaphore:
            client = self._token_manager.get_async_client()
            token = await self._token_manager.ensure_valid_token_async()
            headers = {
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            }

            symbol_path = quote(str(symbol), safe="")
            endpoint = f"/option-chains/{symbol_path}"  # FULL endpoint, not /compact
            url = f"{self._credentials.api_base_url}{endpoint}"

            try:
                response = await client.get(url, headers=headers)

                # Handle common HTTP errors
                if response.status_code == 401:
                    # Token may have expired, refresh and retry
                    token = await self._token_manager.ensure_valid_token_async()
                    headers["Authorization"] = f"Bearer {token}"
                    response = await client.get(url, headers=headers)

                if response.status_code == 404:
                    logger.debug("No option chain available for %s (404 Not Found)", symbol)
                    return symbol, None

                if response.status_code == 429:
                    # Rate limit: exponential backoff
                    await asyncio.sleep(1.0)
                    response = await client.get(url, headers=headers)

                if response.status_code >= 500:
                    logger.error(
                        "Tastytrade server error %s for symbol %s",
                        response.status_code,
                        symbol,
                    )
                    return symbol, None

                response.raise_for_status()
                payload = response.json()
                normalized = self._normalize_option_chain_payload(symbol, payload)
                return symbol, normalized

            except (httpx.HTTPError, ValueError) as e:
                logger.error("Error fetching option chain for %s: %s", symbol, e)
                return symbol, None

    async def _get_option_chains_async(
        self, symbols: list[str], max_concurrent: int = 10
    ) -> dict[str, dict[str, Any]]:
        """
        Fetch option chains for multiple symbols in parallel.

        Args:
            symbols: List of underlying symbols (e.g., ['AAPL', 'SPY'])
            max_concurrent: Maximum concurrent requests (default: 10)

        Returns:
            Dictionary mapping symbol to chain data (filtered to Regular options).
        """
        if not symbols:
            return {}

        # Filter out futures symbols (not supported)
        equity_symbols = [s for s in symbols if s and not str(s).startswith("/")]
        if not equity_symbols:
            return {}

        start_time = time.time()
        logger.debug(
            "API call: /option-chains (parallel) symbols=%s, max_concurrent=%s",
            len(equity_symbols),
            max_concurrent,
        )

        # Create semaphore for rate limiting
        semaphore = asyncio.Semaphore(max_concurrent)

        # Fetch all chains in parallel
        tasks = [self._fetch_option_chain_async(symbol, semaphore) for symbol in equity_symbols]
        results_list = await asyncio.gather(*tasks)

        # Build results dictionary and track failures
        results: dict[str, dict[str, Any]] = {}
        failed_symbols = []
        for symbol, chain in results_list:
            if chain is not None:
                results[symbol] = chain
            else:
                failed_symbols.append(symbol)

        elapsed_ms = (time.time() - start_time) * 1000
        logger.info(
            "API /option-chains (parallel) completed: %s/%s symbols in %.0fms (%.0fms avg)",
            len(results),
            len(equity_symbols),
            elapsed_ms,
            elapsed_ms / len(equity_symbols) if equity_symbols else 0,
        )

        if failed_symbols:
            logger.info(
                "Option chains not available for %s symbols: %s",
                len(failed_symbols),
                ", ".join(failed_symbols),
            )

        return results

    def get_option_chains_compact(self, symbols: list[str]) -> dict[str, dict[str, Any]]:
        """
        Fetch equity option chains for multiple symbols.

        This method:
        1. Checks cache for each symbol first (24-hour TTL)
        2. Fetches only uncached symbols from API
        3. Uses parallel async fetching for multiple symbols
        4. Caches fresh results

        Note: Despite the name, this uses the FULL endpoint (not /compact) because
        the compact endpoint omits intermediate monthly expirations needed for
        Tastylive 30-45 DTE methodology.

        Args:
            symbols: List of underlying symbols (e.g., ['AAPL', 'SPY'])

        Returns:
            Dictionary mapping symbol to chain data (filtered to Regular options).
        """
        if not symbols:
            return {}

        # Filter equity symbols
        equity_symbols = [s for s in symbols if s and not str(s).startswith("/")]
        if not equity_symbols:
            return {}

        # Check cache and partition symbols
        cached_results: dict[str, dict[str, Any]] = {}
        uncached_symbols: list[str] = []

        for symbol in equity_symbols:
            cache_key = make_cache_key("option_chain", symbol)
            cached = self._cache.get(cache_key)
            if cached:
                cached_results[symbol] = cached
            else:
                uncached_symbols.append(symbol)

        # If all symbols are cached, return early
        if not uncached_symbols:
            logger.debug("Cache hit: all %s option chains cached", len(equity_symbols))
            return cached_results

        logger.debug(
            "Cache partial: %s cached, %s uncached of %s total option chains",
            len(cached_results),
            len(uncached_symbols),
            len(equity_symbols),
        )

        # Fetch uncached symbols
        fresh_results: dict[str, dict[str, Any]] = {}

        # Use parallel async fetching for multiple symbols
        if len(uncached_symbols) > 1:
            # Load max_concurrent from config or default to 10
            max_concurrent = 10
            try:
                config_path = Path(__file__).parent.parent.parent / "config" / "runtime_config.json"
                if config_path.exists():
                    with open(config_path) as f:
                        config = json.load(f)
                        max_concurrent = config.get("tastytrade", {}).get(
                            "max_concurrent_option_chains", 10
                        )
            except Exception:
                pass  # Use default if config loading fails

            # Run async version
            fresh_results = asyncio.run(
                self._get_option_chains_async(uncached_symbols, max_concurrent)
            )
        else:
            # Single symbol: use synchronous version (no async overhead)
            start_time = time.time()
            symbol = uncached_symbols[0]
            logger.debug("API call: /option-chains (full) symbol=%s", symbol)
            token = self._token_manager.ensure_valid_token()
            headers = {
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            }

            symbol_path = quote(str(symbol), safe="")
            endpoint = f"/option-chains/{symbol_path}"  # FULL endpoint, not /compact
            url = f"{self._credentials.api_base_url}{endpoint}"
            payload = self._token_manager.fetch_api_data(url, headers, params={})
            normalized = self._normalize_option_chain_payload(symbol, payload)

            if normalized:
                fresh_results[symbol] = normalized

            elapsed_ms = (time.time() - start_time) * 1000
            logger.info(
                "API /option-chains (full) completed: %s in %.0fms",
                symbol,
                elapsed_ms,
            )

        # Cache fresh results
        ttl = get_dynamic_ttl("option_chain", 86400)  # 24 hours (chain structure is stable)
        for symbol, chain in fresh_results.items():
            cache_key = make_cache_key("option_chain", symbol)
            self._cache.set(cache_key, chain, ttl_seconds=ttl)

        # Merge cached and fresh results
        all_results = {**cached_results, **fresh_results}

        logger.info(
            "Option chains completed: %s total (%s cached, %s fetched)",
            len(all_results),
            len(cached_results),
            len(fresh_results),
        )
        return all_results

    def get_futures_option_chain(self, symbol: str) -> list[dict[str, Any]]:
        """
        Fetch full futures option chain data for a single symbol.

        Args:
            symbol: Futures root symbol (e.g., "/ES")

        Returns:
            List of option chain items.
        """
        if not symbol:
            return []

        start_time = time.time()
        logger.debug("API call: /futures-option-chains symbol=%s", symbol)
        token = self._token_manager.ensure_valid_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }
        symbol_path = quote(str(symbol), safe="")
        url = f"{self._credentials.api_base_url}/futures-option-chains/{symbol_path}"
        payload = self._token_manager.fetch_api_data(url, headers, params={})
        items = self._normalize_futures_chain_payload(payload)
        elapsed_ms = (time.time() - start_time) * 1000
        logger.info(
            "API /futures-option-chains completed: %s items in %.0fms",
            len(items),
            elapsed_ms,
        )
        return items

    def find_atm_options(
        self,
        symbol: str,
        chain: dict[str, Any],
        underlying_price: float,
        target_dte: int = 45,
        *,
        dte_min: Optional[int] = None,
        dte_max: Optional[int] = None,
    ) -> Optional[tuple[str, str]]:
        """
        Find ATM call and put OCC symbols from chain.

        Args:
            symbol: Underlying symbol
            chain: Compact chain data from get_option_chains_compact()
            underlying_price: Current underlying price
            target_dte: Target days to expiration (default: 45)
            dte_min: Optional minimum DTE bound
            dte_max: Optional maximum DTE bound

        Returns:
            (call_occ_symbol, put_occ_symbol) if found, otherwise None.
        """
        expirations = chain.get("expirations", [])
        if not expirations:
            return None

        selected = self._select_expiration(expirations, target_dte, dte_min, dte_max)
        if not selected:
            return None
        expiration, exp_date = selected

        strikes = self._extract_strikes(expiration)
        if not strikes:
            return None
        atm_strike = min(strikes, key=lambda s: abs(s - underlying_price))

        if str(symbol).startswith("/"):
            futures_symbols = self._find_futures_option_symbols(expiration, atm_strike)
            if futures_symbols:
                return futures_symbols
            return None

        root = (
            chain.get("option_root_symbol")
            or chain.get("root_symbol")
            or chain.get("underlying_symbol")
            or chain.get("symbol")
            or symbol
        )
        if not exp_date:
            return None

        call_symbol = self.build_occ_symbol(root, exp_date, atm_strike, "C")
        put_symbol = self.build_occ_symbol(root, exp_date, atm_strike, "P")
        return call_symbol, put_symbol

    def find_futures_atm_options(
        self,
        chain_items: list[dict[str, Any]],
        underlying_price: float,
        target_dte: int = 45,
        *,
        dte_min: Optional[int] = None,
        dte_max: Optional[int] = None,
    ) -> Optional[tuple[str, str]]:
        """
        Find ATM call/put symbols from a futures option chain.

        Args:
            chain_items: Futures option chain items
            underlying_price: Current underlying price
            target_dte: Target days to expiration (default: 45)
            dte_min: Optional minimum DTE bound
            dte_max: Optional maximum DTE bound

        Returns:
            (call_symbol, put_symbol) if found, otherwise None.
        """
        if not chain_items:
            return None

        candidates: list[tuple[dict[str, Any], int]] = []
        for item in chain_items:
            if not isinstance(item, dict):
                continue
            dte_val = self._extract_dte(item)
            if dte_val is None:
                continue
            if dte_min is not None and dte_val < dte_min:
                continue
            if dte_max is not None and dte_val > dte_max:
                continue
            candidates.append((item, dte_val))

        if not candidates:
            return None

        target_exp = min(candidates, key=lambda item: abs(item[1] - target_dte))[0]
        exp_date = (
            target_exp.get("expiration-date")
            or target_exp.get("expiration_date")
            or target_exp.get("expiration")
        )

        exp_items = []
        for item in chain_items:
            if not isinstance(item, dict):
                continue
            item_exp = (
                item.get("expiration-date") or item.get("expiration_date") or item.get("expiration")
            )
            if exp_date and item_exp != exp_date:
                continue
            exp_items.append(item)

        if not exp_items:
            return None

        strikes: list[float] = []
        for item in exp_items:
            strike = self._extract_strike(item)
            if strike is not None:
                strikes.append(strike)

        if not strikes:
            return None

        atm_strike = min(strikes, key=lambda s: abs(s - underlying_price))

        call_symbol = None
        put_symbol = None
        for item in exp_items:
            strike = self._extract_strike(item)
            if strike is None or abs(strike - atm_strike) > 1e-6:
                continue
            option_type = self._extract_option_type(item)
            symbol = item.get("symbol")
            if not symbol:
                continue
            if option_type == "C":
                call_symbol = symbol
            elif option_type == "P":
                put_symbol = symbol

        if call_symbol and put_symbol:
            return call_symbol, put_symbol
        return None

    @staticmethod
    def build_occ_symbol(symbol: str, expiration: date, strike: float, call_put: str) -> str:
        """
        Build OCC option symbol for equities.

        Format: SYMBOL(6) + YYMMDD + C/P + STRIKE(8, *1000)
        Example: AAPL  260220C00170000
        """
        root = str(symbol).upper().replace("/", "")
        root = root.replace(".", "")
        root = root[:6].ljust(6)
        exp = expiration.strftime("%y%m%d")
        strike_int = int(round(strike * 1000))
        strike_str = f"{strike_int:08d}"
        return f"{root}{exp}{call_put.upper()}{strike_str}"

    def _normalize_option_chain_payload(
        self, symbol: str, payload: Any
    ) -> Optional[dict[str, Any]]:
        """
        Normalize raw option chain payloads into a compact, predictable structure.

        Handles both:
        - Full endpoint: individual option contracts that need grouping
        - Compact endpoint: pre-grouped expirations (legacy)
        """
        if payload is None:
            return None

        data = payload.get("data", payload) if isinstance(payload, dict) else payload
        if not isinstance(data, dict):
            return None

        items = data.get("items", [])
        if not isinstance(items, list) or not items:
            return None

        # Detect if these are individual options or grouped expirations
        first_item = items[0] if items else {}
        is_individual_options = "strike-price" in first_item

        if is_individual_options:
            # Full endpoint: Group individual options by expiration
            return self._group_options_by_expiration(symbol, items)
        else:
            # Compact endpoint (legacy): Already grouped
            return self._normalize_grouped_expirations(symbol, items, data)

    def _group_options_by_expiration(
        self, symbol: str, options: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Group individual option contracts by expiration date."""
        # Filter to Regular/Quarterly (except major indexes)
        major_symbols = {"SPY", "QQQ", "SPX", "/ES", "/NQ", "DIA", "IWM"}
        if symbol not in major_symbols:
            options = [
                opt for opt in options if opt.get("expiration-type") in ("Regular", "Quarterly")
            ]

        # Group by expiration date
        by_expiration: dict[str, dict[str, Any]] = defaultdict(
            lambda: {"symbols": [], "strikes": set()}
        )

        for opt in options:
            exp_date = opt.get("expiration-date")
            if not exp_date:
                continue

            exp_group = by_expiration[exp_date]
            exp_group["expiration-date"] = exp_date
            exp_group["days-to-expiration"] = opt.get("days-to-expiration")
            exp_group["expiration-type"] = opt.get("expiration-type")

            # Collect symbols and strikes
            opt_symbol = opt.get("symbol")
            if opt_symbol:
                exp_group["symbols"].append(opt_symbol)

            strike = opt.get("strike-price")
            if strike:
                try:
                    exp_group["strikes"].add(float(strike))
                except (TypeError, ValueError):
                    pass

        # Convert to final structure
        expirations = []
        for exp_date in sorted(by_expiration.keys()):
            exp = by_expiration[exp_date]
            exp["strikes"] = sorted(list(exp["strikes"]))
            expirations.append(exp)

        return {
            "symbol": symbol,
            "underlying_symbol": symbol,
            "root_symbol": symbol,
            "expirations": expirations,
        }

    def _normalize_grouped_expirations(
        self, symbol: str, items: list[dict[str, Any]], data: dict[str, Any]
    ) -> dict[str, Any]:
        """Normalize pre-grouped expirations from compact endpoint (legacy)."""
        underlying_symbol = (
            data.get("underlying-symbol")
            or data.get("underlying_symbol")
            or data.get("symbol")
            or symbol
        )
        root_symbol = (
            data.get("option-root-symbol")
            or data.get("option_root_symbol")
            or data.get("root-symbol")
            or data.get("root_symbol")
            or underlying_symbol
        )

        # Filter to Regular options only (exclude Weeklies)
        major_symbols = {"SPY", "QQQ", "SPX", "/ES", "/NQ", "DIA", "IWM"}
        if symbol not in major_symbols:
            items = [
                exp
                for exp in items
                if isinstance(exp, dict)
                and exp.get("expiration-type") in ("Regular", "Quarterly", None)
            ]

        # Parse OCC symbols if expiration data missing (legacy fallback)
        for exp_item in items:
            if not isinstance(exp_item, dict):
                continue
            if exp_item.get("expiration-date") and exp_item.get("days-to-expiration"):
                continue

            symbols_list = exp_item.get("symbols", [])
            if symbols_list and isinstance(symbols_list, list):
                first_symbol = str(symbols_list[0])
                if len(first_symbol) >= 12:
                    date_part = first_symbol[6:12]
                    try:
                        exp_date = datetime.strptime(f"20{date_part}", "%Y%m%d").date()
                        dte = (exp_date - date.today()).days
                        exp_item["expiration-date"] = exp_date.isoformat()
                        exp_item["days-to-expiration"] = dte
                    except (ValueError, AttributeError):
                        pass

        return {
            "symbol": symbol,
            "underlying_symbol": underlying_symbol,
            "root_symbol": root_symbol,
            "expirations": items,
        }

    @staticmethod
    def _normalize_futures_chain_payload(payload: Any) -> list[dict[str, Any]]:
        """Normalize futures option chain payload into a list of items."""
        if payload is None:
            return []
        data = payload.get("data", payload) if isinstance(payload, dict) else payload
        if isinstance(data, dict):
            items = data.get("items")
        elif isinstance(data, list):
            items = data
        else:
            items = None
        return items if isinstance(items, list) else []

    def _select_expiration(
        self,
        expirations: list[Any],
        target_dte: int,
        dte_min: Optional[int],
        dte_max: Optional[int],
    ) -> Optional[tuple[dict[str, Any], Optional[date]]]:
        """Select the expiration closest to target DTE within optional bounds."""
        candidates: list[tuple[dict[str, Any], int, Optional[date]]] = []
        for exp in expirations:
            if not isinstance(exp, dict):
                continue
            dte = exp.get("days-to-expiration") or exp.get("days_to_expiration")
            exp_date = self._parse_expiration_date(exp)
            if dte is None and exp_date:
                dte = (exp_date - date.today()).days
            if dte is None:
                continue
            try:
                dte_val = int(float(dte))
            except (TypeError, ValueError):
                continue
            if dte_min is not None and dte_val < dte_min:
                continue
            if dte_max is not None and dte_val > dte_max:
                continue
            candidates.append((exp, dte_val, exp_date))

        if not candidates:
            return None

        exp, _dte, exp_date = min(candidates, key=lambda item: abs(item[1] - target_dte))
        return exp, exp_date

    def _parse_expiration_date(self, expiration: dict[str, Any]) -> Optional[date]:
        """Parse an expiration date from chain metadata."""
        raw = expiration.get("expiration-date") or expiration.get("expiration_date")
        if not raw:
            return None
        if isinstance(raw, date):
            return raw
        if isinstance(raw, datetime):
            return raw.date()
        try:
            return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).date()
        except ValueError:
            try:
                return datetime.strptime(str(raw), "%Y-%m-%d").date()
            except ValueError:
                return None

    def _extract_strikes(self, expiration: dict[str, Any]) -> list[float]:
        """Extract numeric strikes from chain expiration."""
        # Try explicit strikes field first (from full endpoint grouping)
        strikes_raw = expiration.get("strikes")
        if isinstance(strikes_raw, list) and strikes_raw:
            # Already sorted floats from _group_options_by_expiration
            return strikes_raw

        # Try other strike field names (legacy compact endpoint)
        strikes_raw = expiration.get("strike-prices") or expiration.get("strike_prices")
        if isinstance(strikes_raw, list):
            strikes: list[float] = []
            for strike in strikes_raw:
                try:
                    strikes.append(float(strike))
                except (TypeError, ValueError):
                    continue
            return sorted(strikes)

        # Final fallback: Parse from OCC symbols
        symbols_list = expiration.get("symbols", [])
        if isinstance(symbols_list, list) and symbols_list:
            strikes_set: set[float] = set()
            for occ_symbol in symbols_list:
                occ_str = str(occ_symbol)
                # OCC format: "SYMBOL  YYMMDDCTTTTTTKKKK"
                # Characters 13-20 = strike * 1000 (8 digits)
                if len(occ_str) >= 21:
                    try:
                        strike_str = occ_str[13:21]
                        strike_int = int(strike_str)
                        strike = strike_int / 1000.0
                        strikes_set.add(strike)
                    except (ValueError, IndexError):
                        continue
            return sorted(list(strikes_set))

        return []

    def _find_futures_option_symbols(
        self, expiration: dict[str, Any], strike: float
    ) -> Optional[tuple[str, str]]:
        """Locate futures option symbols for the selected strike when available."""
        options = (
            expiration.get("options")
            or expiration.get("option-symbols")
            or expiration.get("option_symbols")
        )
        if not isinstance(options, list):
            return None

        call_symbol = None
        put_symbol = None
        for option in options:
            if not isinstance(option, dict):
                continue
            strike_val = (
                option.get("strike") or option.get("strike-price") or option.get("strike_price")
            )
            if strike_val is None:
                continue
            try:
                strike_float = float(strike_val)
            except (TypeError, ValueError):
                continue
            if abs(strike_float - strike) > 1e-6:
                continue
            option_type = (
                option.get("option-type")
                or option.get("option_type")
                or option.get("type")
                or option.get("call-put")
            )
            symbol = (
                option.get("symbol") or option.get("option-symbol") or option.get("streamer-symbol")
            )
            if not symbol:
                continue
            if str(option_type).upper().startswith("C"):
                call_symbol = symbol
            elif str(option_type).upper().startswith("P"):
                put_symbol = symbol

        if call_symbol and put_symbol:
            return call_symbol, put_symbol
        return None

    def _extract_dte(self, item: dict[str, Any]) -> Optional[int]:
        """Extract DTE from futures chain item."""
        dte = item.get("days-to-expiration") or item.get("days_to_expiration")
        if dte is not None:
            try:
                return int(float(dte))
            except (TypeError, ValueError):
                return None
        exp_date = self._parse_expiration_date(item)
        if not exp_date:
            return None
        return (exp_date - date.today()).days

    @staticmethod
    def _extract_strike(item: dict[str, Any]) -> Optional[float]:
        """Extract strike price from futures chain item."""
        strike = item.get("strike-price") or item.get("strike_price") or item.get("strike")
        if strike is None:
            return None
        try:
            return float(strike)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _extract_option_type(item: dict[str, Any]) -> Optional[str]:
        """Extract option type (C/P) from futures chain item."""
        option_type = (
            item.get("option-type")
            or item.get("option_type")
            or item.get("type")
            or item.get("call-put")
        )
        if not option_type:
            return None
        option_type = str(option_type).upper()
        if option_type.startswith("C"):
            return "C"
        if option_type.startswith("P"):
            return "P"
        return None
