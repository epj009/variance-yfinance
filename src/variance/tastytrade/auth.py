"""
OAuth Authentication and Token Management for Tastytrade API.

This module provides:
- TastytradeCredentials: OAuth credentials container
- TastytradeAuthError: Authentication exception
- TastytradeMetrics: Market metrics TypedDict
- TokenManager: Token lifecycle and API fetching
"""

import asyncio
import logging
import os
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Optional, TypedDict

try:
    import requests
except ModuleNotFoundError:
    raise ImportError("Missing dependency 'requests'. Install with: pip install requests") from None

try:
    import httpx
except ModuleNotFoundError:
    raise ImportError("Missing dependency 'httpx'. Install with: pip install httpx") from None

logger = logging.getLogger(__name__)


class TastytradeAuthError(Exception):
    """Raised when OAuth authentication fails or credentials are missing."""

    pass


@dataclass(frozen=True)
class TastytradeCredentials:
    """OAuth credentials for Tastytrade API."""

    client_id: str
    client_secret: str
    refresh_token: str
    api_base_url: str = "https://api.tastytrade.com"

    @classmethod
    def from_environment(cls) -> "TastytradeCredentials":
        """
        Load credentials from environment variables.

        Environment Variables:
            TT_CLIENT_ID: OAuth client ID
            TT_CLIENT_SECRET: OAuth client secret
            TT_REFRESH_TOKEN: OAuth refresh token (long-lived)
            API_BASE_URL: Tastytrade API base URL (optional)

        Returns:
            TastytradeCredentials instance

        Raises:
            TastytradeAuthError: If required environment variables are missing
        """
        client_id = os.getenv("TT_CLIENT_ID")
        client_secret = os.getenv("TT_CLIENT_SECRET")
        refresh_token = os.getenv("TT_REFRESH_TOKEN")

        missing_vars = []
        if not client_id:
            missing_vars.append("TT_CLIENT_ID")
        if not client_secret:
            missing_vars.append("TT_CLIENT_SECRET")
        if not refresh_token:
            missing_vars.append("TT_REFRESH_TOKEN")

        if missing_vars:
            raise TastytradeAuthError(
                f"Missing required environment variables: {', '.join(missing_vars)}"
            )

        # mypy: After error check, these are guaranteed to be str
        assert client_id is not None
        assert client_secret is not None
        assert refresh_token is not None

        api_base_url = os.getenv("API_BASE_URL", "https://api.tastytrade.com")
        if not api_base_url.startswith("http"):
            api_base_url = f"https://{api_base_url}"

        return cls(
            client_id=client_id,
            client_secret=client_secret,
            refresh_token=refresh_token,
            api_base_url=api_base_url,
        )


class TastytradeMetrics(TypedDict, total=False):
    """
    Tastytrade market metrics response structure.

    Fields are mapped from Tastytrade API response to Variance internal format.
    """

    # Core volatility metrics
    iv: Optional[float]  # Implied volatility (converted to percent)
    iv_rank: Optional[float]  # IV rank (0-100)
    iv_percentile: Optional[float]  # IV percentile (0-100)
    hv30: Optional[float]  # 30-day historical volatility (percent)
    hv90: Optional[float]  # 90-day historical volatility (percent)

    # Liquidity metrics
    liquidity_rating: Optional[int]  # Liquidity rating (0-5)
    liquidity_value: Optional[float]  # Liquidity value score
    option_volume: Optional[float]  # 30-day average option volume

    # Correlation
    corr_spy_3month: Optional[float]  # 3-month correlation with SPY

    # Greeks (optional)
    beta: Optional[float]  # Beta vs market

    # Earnings
    earnings_date: Optional[str]  # Expected earnings report date (YYYY-MM-DD)

    # Metadata
    symbol: str  # Ticker symbol
    updated_at: Optional[str]  # Timestamp of last update


class TokenManager:
    """
    Manages OAuth token lifecycle and API requests.

    Handles:
    - Token refresh using OAuth 2.0 refresh token grant
    - Token expiry tracking and automatic renewal
    - Async client management for parallel requests
    - Public API access for FuturesSymbolResolver
    """

    def __init__(self, credentials: TastytradeCredentials):
        """
        Initialize token manager.

        Args:
            credentials: OAuth credentials for Tastytrade API
        """
        self._credentials = credentials
        self._access_token: Optional[str] = None
        self._token_expiry: float = 0.0
        self._async_client: Optional[httpx.AsyncClient] = None
        self._async_token_lock = asyncio.Lock()

    def _refresh_access_token(self) -> None:
        """
        Refresh the OAuth access token using the refresh token.

        Uses the OAuth 2.0 refresh token grant to obtain a new access token.
        Updates internal state with new token and expiry time.

        Raises:
            TastytradeAuthError: If token refresh fails (invalid credentials, network error)
        """
        url = f"{self._credentials.api_base_url}/oauth/token"
        payload = {
            "grant_type": "refresh_token",
            "refresh_token": self._credentials.refresh_token,
            "client_id": self._credentials.client_id,
            "client_secret": self._credentials.client_secret,
        }

        try:
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            raise TastytradeAuthError(f"OAuth token refresh failed: {e}") from e

        try:
            data = response.json()
            self._access_token = data["access_token"]
            # expires_in is in seconds, add buffer of 60s
            expires_in = data.get("expires_in", 3600)
            self._token_expiry = time.time() + expires_in - 60
        except (KeyError, ValueError) as e:
            raise TastytradeAuthError(f"Invalid OAuth response format: {e}") from e

    def ensure_valid_token(self) -> str:
        """
        Ensure a valid access token is available, refreshing if necessary.

        Returns:
            Valid access token

        Raises:
            TastytradeAuthError: If token refresh fails
        """
        if not self._access_token or time.time() >= self._token_expiry:
            self._refresh_access_token()

        # Type guard: _refresh_access_token ensures token is set
        assert self._access_token is not None
        return self._access_token

    async def ensure_valid_token_async(self) -> str:
        """
        Async version of ensure_valid_token with lock protection.

        Returns:
            Valid access token

        Raises:
            TastytradeAuthError: If token refresh fails
        """
        async with self._async_token_lock:
            # Check again inside lock (double-check locking pattern)
            if not self._access_token or time.time() >= self._token_expiry:
                self._refresh_access_token()

            # Type guard: _refresh_access_token ensures token is set
            assert self._access_token is not None
            return self._access_token

    def get_async_client(self) -> httpx.AsyncClient:
        """
        Get or create the async HTTP client for parallel requests.

        Returns:
            Shared AsyncClient instance
        """
        if self._async_client is None:
            self._async_client = httpx.AsyncClient(timeout=15.0)
        return self._async_client

    # PUBLIC methods for FuturesSymbolResolver (CRITICAL FIX)
    def get_token(self) -> str:
        """
        Public access to token for FuturesSymbolResolver.

        Returns:
            Valid access token
        """
        return self.ensure_valid_token()

    def fetch_api_data(
        self, url: str, headers: dict[str, str], params: Mapping[str, str | list[str]]
    ) -> Optional[Any]:
        """
        Public API fetcher for FuturesSymbolResolver.

        Fetch data from Tastytrade API with error handling.

        Args:
            url: API endpoint URL
            headers: HTTP headers including auth token
            params: Query parameters (values can be strings or lists of strings)

        Returns:
            JSON response as dict, or None if error
        """
        try:
            response = requests.get(url, headers=headers, params=params, timeout=15)

            # Handle common HTTP errors
            if response.status_code == 401:
                # Token may have expired prematurely, try once more
                self._access_token = None
                token = self.ensure_valid_token()
                headers["Authorization"] = f"Bearer {token}"
                response = requests.get(url, headers=headers, params=params, timeout=15)

            if response.status_code == 404:
                return None

            if response.status_code == 429:
                # Rate limit hit - implement exponential backoff
                retry_after = int(response.headers.get("Retry-After", 5))
                retry_after = min(retry_after, 60)  # Cap at 60 seconds
                logger.warning(f"Rate limit hit (429), retrying after {retry_after}s")
                time.sleep(retry_after)

                # Retry once
                token = self.ensure_valid_token()
                headers["Authorization"] = f"Bearer {token}"
                response = requests.get(url, headers=headers, params=params, timeout=15)

                if response.status_code == 429:
                    raise requests.exceptions.RequestException(
                        f"Rate limit exceeded after retry. Waited {retry_after}s."
                    )

            if response.status_code >= 500:
                raise requests.exceptions.RequestException(
                    f"Tastytrade server error: {response.status_code}"
                )

            response.raise_for_status()
            return response.json()

        except (requests.exceptions.RequestException, ValueError) as e:
            logger.error("Tastytrade API error: %s", e)
            return None

    @property
    def api_base_url(self) -> str:
        """
        Public access to base URL.

        Returns:
            API base URL
        """
        return self._credentials.api_base_url

    async def close_async(self) -> None:
        """Close the async HTTP client (async version)."""
        if self._async_client is not None:
            await self._async_client.aclose()
            self._async_client = None

    def close(self) -> None:
        """
        Close the async HTTP client and cleanup resources.

        Should be called when the token manager is no longer needed.
        """
        if self._async_client is not None:
            import asyncio

            asyncio.run(self.close_async())


# Utility methods (static helpers)
def _safe_float(value: Any) -> Optional[float]:
    """Convert value to float, returning None on error."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> Optional[int]:
    """Convert value to int, returning None on error."""
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _normalize_hv(value: Optional[float]) -> Optional[float]:
    """
    Normalize historical volatility from decimal to percent if needed.

    Args:
        value: HV value (may be decimal or percent)

    Returns:
        HV value normalized to percent (0-100 scale)
    """
    if value is None:
        return None
    # REST HV values are returned as decimals (0.25 => 25%); normalize to percent.
    return value * 100.0 if value <= 2.0 else value
