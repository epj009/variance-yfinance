"""
Futures Symbol Resolution for DXLink Streaming.

Resolves futures root symbols (e.g., /ES) to DXLink streamer symbols
required for historical volatility calculation via WebSocket.
"""

import re
from typing import TYPE_CHECKING, Any, Optional
from urllib.parse import quote

if TYPE_CHECKING:
    from ..tastytrade_client import TastytradeClient


class FuturesSymbolResolver:
    """
    Resolve futures symbols to DXLink streamer format.

    Handles:
    - Root symbol to active contract resolution (/ES -> /ESH25)
    - Contract to streamer symbol resolution (/ESH25 -> /ES:XCME:H25)
    - Historical chain resolution for stitching multiple contracts
    """

    def __init__(self, api_client: "TastytradeClient"):
        """
        Initialize futures symbol resolver.

        Args:
            api_client: TastytradeClient instance for API access
        """
        self.api = api_client
        self._cache: dict[str, Optional[str]] = {}
        self._futures_list_cache: Optional[list[dict[str, Any]]] = None

    def resolve_to_dxlink(self, symbol: str) -> Optional[str]:
        """
        Resolve a futures symbol to DXLink streamer format.

        Args:
            symbol: Futures root or contract symbol (e.g., /ES or /ESH25)

        Returns:
            DXLink streamer symbol (e.g., /ES:XCME:H25) or None
        """
        if not symbol or not symbol.startswith("/"):
            return None

        cache_key = symbol.upper()
        if cache_key in self._cache:
            return self._cache[cache_key]

        resolved = self._resolve_future_streamer_symbol(symbol)
        self._cache[cache_key] = resolved
        return resolved

    def resolve_history_chain(self, symbol: str) -> list[str]:
        """
        Resolve futures symbol to historical contract chain for stitching.

        Returns the active contract and previous contract for continuous
        historical volatility calculation.

        Args:
            symbol: Futures root symbol (e.g., /ES)

        Returns:
            List of DXLink streamer symbols (up to 2 contracts)
        """
        if not symbol or not symbol.startswith("/"):
            return []

        root_symbol = self._normalize_future_root(symbol)
        if not root_symbol:
            return []

        items = self._fetch_futures_list()
        candidates = []
        for item in items:
            item_symbol = item.get("symbol")
            if not isinstance(item_symbol, str):
                continue
            normalized = self._normalize_future_root(item_symbol)
            if normalized and normalized.upper() == root_symbol.upper():
                if self._extract_streamer_symbol(item):
                    candidates.append(item)

        if not candidates:
            active = self.resolve_to_dxlink(symbol)
            return [active] if active else []

        def parse_expiration(item: dict[str, Any]) -> Optional[str]:
            return item.get("expiration-date") or item.get("expiration_date")

        candidates = [c for c in candidates if parse_expiration(c)]
        candidates.sort(
            key=lambda c: parse_expiration(c) or "",
            reverse=True,
        )

        active_item = next((c for c in candidates if c.get("active-month")), None)
        if not active_item and candidates:
            active_item = candidates[0]

        history_items = []
        if active_item:
            history_items.append(active_item)
            try:
                idx = candidates.index(active_item)
            except ValueError:
                idx = 0
            if idx + 1 < len(candidates):
                history_items.append(candidates[idx + 1])

        history_symbols = []
        for item in history_items:
            streamer = self._extract_streamer_symbol(item)
            if streamer and streamer not in history_symbols:
                history_symbols.append(streamer)

        return history_symbols

    def _resolve_future_streamer_symbol(self, symbol: str) -> Optional[str]:
        """
        Resolve a futures root or contract symbol to DXLink streamer symbol.

        Args:
            symbol: Futures symbol (/ES or /ESH25)

        Returns:
            Streamer symbol (/ES:XCME:H25) or None
        """
        if self._is_future_contract(symbol):
            item = self._fetch_future_instrument(symbol)
            streamer = self._extract_streamer_symbol(item)
            if streamer:
                return streamer

        root = self._normalize_future_root(symbol)
        if root:
            contract_symbol = self._resolve_future_contract_symbol(root)
            if contract_symbol:
                if self._looks_like_streamer_symbol(contract_symbol):
                    return contract_symbol
                item = self._fetch_future_instrument(contract_symbol)
                streamer = self._extract_streamer_symbol(item)
                if streamer:
                    return streamer
            streamer = self._resolve_active_streamer_from_list(root)
            if streamer:
                return streamer

        return None

    def _fetch_future_instrument(self, symbol: str) -> Optional[dict[str, Any]]:
        """Fetch futures instrument metadata from API."""
        if not symbol:
            return None

        token = self.api._ensure_valid_token()
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        encoded_symbol = quote(symbol, safe="")
        url = f"{self.api._credentials.api_base_url}/instruments/futures/{encoded_symbol}"

        data = self.api._fetch_api_data(url, headers, params={})
        if not data:
            return None

        if isinstance(data, list) and data:
            return data[0]

        if not isinstance(data, dict):
            return None

        data_block = data.get("data", {})
        if isinstance(data_block, dict):
            item = data_block.get("item")
            if isinstance(item, dict):
                return item
            items = data_block.get("items")
            if isinstance(items, list) and items:
                if isinstance(items[0], dict):
                    return items[0]

        return None

    def _fetch_future_products(self) -> list[dict[str, Any]]:
        """Fetch list of all futures products from API."""
        token = self.api._ensure_valid_token()
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        url = f"{self.api._credentials.api_base_url}/instruments/future-products"

        data = self.api._fetch_api_data(url, headers, params={})
        if not data or not isinstance(data, dict):
            return []

        items = data.get("data", {}).get("items", [])
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]

        return []

    def _fetch_futures_list(self) -> list[dict[str, Any]]:
        """Fetch list of all futures contracts (cached)."""
        if self._futures_list_cache is not None:
            return self._futures_list_cache

        token = self.api._ensure_valid_token()
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        url = f"{self.api._credentials.api_base_url}/instruments/futures"

        data = self.api._fetch_api_data(url, headers, params={})
        if not data or not isinstance(data, dict):
            self._futures_list_cache = []
            return self._futures_list_cache

        items = data.get("data", {}).get("items", [])
        if isinstance(items, list):
            self._futures_list_cache = [item for item in items if isinstance(item, dict)]
        else:
            self._futures_list_cache = []
        return self._futures_list_cache

    def _resolve_active_streamer_from_list(self, root_symbol: str) -> Optional[str]:
        """Resolve active contract streamer symbol from futures list."""
        root_symbol = root_symbol.upper()
        items = self._fetch_futures_list()
        if not items:
            return None

        def matches_root(item_symbol: str) -> bool:
            normalized = self._normalize_future_root(item_symbol)
            if not normalized:
                return False
            return normalized.upper() == root_symbol

        candidates = []
        for item in items:
            symbol = item.get("symbol")
            if not isinstance(symbol, str):
                continue
            if not matches_root(symbol):
                continue
            candidates.append(item)

        if not candidates:
            return None

        active = [c for c in candidates if c.get("active-month")]
        if not active:
            active = [c for c in candidates if c.get("next-active-month")]
        if not active:
            active = candidates

        for item in active:
            streamer = self._extract_streamer_symbol(item)
            if streamer:
                return streamer

        return None

    def _resolve_future_contract_symbol(self, root_symbol: str) -> Optional[str]:
        """Resolve root symbol to active contract symbol via products endpoint."""
        root_symbol = root_symbol.upper()
        products = self._fetch_future_products()
        for item in products:
            item_root = self._get_any_key(
                item, ("root-symbol", "root_symbol", "symbol", "rootSymbol")
            )
            if not item_root:
                continue
            item_root_str = str(item_root).upper()
            if not item_root_str.startswith("/"):
                item_root_str = f"/{item_root_str}"
            if item_root_str != root_symbol:
                continue

            contract_symbol = self._get_any_key(
                item,
                (
                    "active-contract-symbol",
                    "active_contract_symbol",
                    "active-month-symbol",
                    "active_month_symbol",
                    "front-month-symbol",
                    "front_month_symbol",
                    "near-month-symbol",
                    "near_month_symbol",
                    "active-symbol",
                    "active_symbol",
                ),
            )
            if contract_symbol:
                return str(contract_symbol)

        return None

    @staticmethod
    def _extract_streamer_symbol(item: Optional[dict[str, Any]]) -> Optional[str]:
        """Extract streamer symbol from API response item."""
        if not item:
            return None
        streamer = FuturesSymbolResolver._get_any_key(
            item, ("streamer-symbol", "streamer_symbol", "streamerSymbol")
        )
        return str(streamer) if streamer else None

    @staticmethod
    def _normalize_future_root(symbol: str) -> Optional[str]:
        """
        Normalize futures symbol to root symbol.

        Examples:
            /ESH25 -> /ES
            /ES -> /ES
            /NGM24 -> /NG
        """
        if not symbol:
            return None
        if not symbol.startswith("/"):
            symbol = f"/{symbol}"
        match = re.match(r"^(/[A-Z0-9]{1,3})[FGHJKMNQUVXZ]\d{1,2}$", symbol.upper())
        if match:
            return match.group(1)
        return symbol

    @staticmethod
    def _is_future_contract(symbol: str) -> bool:
        """Check if symbol is a specific futures contract (not root)."""
        if not symbol:
            return False
        return bool(re.match(r"^/[A-Z0-9]{1,3}[FGHJKMNQUVXZ]\d{1,2}$", symbol.upper()))

    @staticmethod
    def _looks_like_streamer_symbol(symbol: str) -> bool:
        """Check if symbol is already in streamer format."""
        return ":" in symbol

    @staticmethod
    def _get_any_key(item: dict[str, Any], keys: tuple[str, ...]) -> Optional[Any]:
        """Get first non-None value from a list of possible keys."""
        for key in keys:
            if key in item:
                value = item.get(key)
                if value is not None:
                    return value
        return None
