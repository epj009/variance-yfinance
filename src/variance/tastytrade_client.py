"""
Tastytrade OAuth API Client for Market Metrics.

This module provides a client for accessing Tastytrade's /market-metrics endpoint
using OAuth 2.0 authentication. It handles token refresh, IV scaling, and error handling.
"""

import os
import time
from typing import Any, Optional, TypedDict

try:
    import requests
except ModuleNotFoundError:
    raise ImportError("Missing dependency 'requests'. Install with: pip install requests") from None


class TastytradeAuthError(Exception):
    """Raised when OAuth authentication fails or credentials are missing."""

    pass


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

    # Correlation
    corr_spy_3month: Optional[float]  # 3-month correlation with SPY

    # Greeks (optional)
    beta: Optional[float]  # Beta vs market

    # Earnings
    earnings_date: Optional[str]  # Expected earnings report date (YYYY-MM-DD)

    # Metadata
    symbol: str  # Ticker symbol
    updated_at: Optional[str]  # Timestamp of last update


class TastytradeClient:
    """
    OAuth-authenticated client for Tastytrade market metrics API.

    This client handles:
    - OAuth token refresh using client credentials + refresh token
    - IV scaling from decimal (0.35) to percent (35.0)
    - Rate limiting and error handling
    - Batch symbol queries

    Environment Variables:
        TT_CLIENT_ID: OAuth client ID
        TT_CLIENT_SECRET: OAuth client secret
        TT_REFRESH_TOKEN: OAuth refresh token (long-lived)
        API_BASE_URL: Tastytrade API base URL (e.g., https://api.tastytrade.com)

    Raises:
        TastytradeAuthError: If credentials are missing or authentication fails
    """

    def __init__(self) -> None:
        """
        Initialize the Tastytrade client.

        Loads OAuth credentials from environment variables and validates presence.

        Raises:
            TastytradeAuthError: If required environment variables are missing
        """
        self.client_id = os.getenv("TT_CLIENT_ID")
        self.client_secret = os.getenv("TT_CLIENT_SECRET")
        self.refresh_token = os.getenv("TT_REFRESH_TOKEN")
        self.api_base_url = os.getenv("API_BASE_URL", "https://api.tastytrade.com")
        if not self.api_base_url.startswith("http"):
            self.api_base_url = f"https://{self.api_base_url}"

        # Validate required credentials
        missing_vars = []
        if not self.client_id:
            missing_vars.append("TT_CLIENT_ID")
        if not self.client_secret:
            missing_vars.append("TT_CLIENT_SECRET")
        if not self.refresh_token:
            missing_vars.append("TT_REFRESH_TOKEN")

        if missing_vars:
            raise TastytradeAuthError(
                f"Missing required environment variables: {', '.join(missing_vars)}"
            )

        # OAuth state
        self._access_token: Optional[str] = None
        self._token_expiry: float = 0.0

    def _refresh_access_token(self) -> None:
        """
        Refresh the OAuth access token using the refresh token.

        Uses the OAuth 2.0 refresh token grant to obtain a new access token.
        Updates internal state with new token and expiry time.

        Raises:
            TastytradeAuthError: If token refresh fails (invalid credentials, network error)
        """
        url = f"{self.api_base_url}/oauth/token"
        payload = {
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
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

    def _ensure_valid_token(self) -> str:
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

    def _parse_metric_item(self, item: Any) -> Optional[TastytradeMetrics]:
        """
        Parse a single market metrics item from Tastytrade API response.

        Args:
            item: Raw metric item from API response

        Returns:
            TastytradeMetrics if symbol is valid, None otherwise
        """
        symbol = item.get("symbol", "").upper()
        if not symbol:
            return None

        metrics: TastytradeMetrics = {"symbol": symbol}

        # HV30 & HV90 (Parse first for context)
        hv30_val: Optional[float] = None
        hv30 = item.get("historical-volatility-30-day")
        if hv30 is not None:
            try:
                hv30_val = float(hv30)
                metrics["hv30"] = hv30_val
            except (ValueError, TypeError):
                pass

        hv90_val: Optional[float] = None
        hv90 = item.get("historical-volatility-90-day")
        if hv90 is not None:
            try:
                hv90_val = float(hv90)
                metrics["hv90"] = hv90_val
            except (ValueError, TypeError):
                pass

        # IV: Context-Aware Scaling
        raw_iv = item.get("implied-volatility-index")
        if raw_iv is not None:
            try:
                val = float(raw_iv)
                if val > 0:
                    # Determine if we should scale by 100
                    # Use HV as anchor if available
                    anchor_vol = hv30_val if hv30_val else hv90_val

                    if val < 1.0:
                        # Hard rule: No equity/commodity has < 1% IV. Assume decimal.
                        metrics["iv"] = val * 100.0
                    elif anchor_vol and anchor_vol > 0:
                        diff_unscaled = abs(val - anchor_vol)
                        diff_scaled = abs((val * 100.0) - anchor_vol)

                        if diff_scaled < diff_unscaled:
                            metrics["iv"] = val * 100.0
                        else:
                            metrics["iv"] = val
                    else:
                        # Fallback heuristic: If < 5.0, assume decimal (500% cutoff)
                        if val < 5.0:
                            metrics["iv"] = val * 100.0
                        else:
                            metrics["iv"] = val
            except (ValueError, TypeError):
                pass

        # IV Rank & Percentile (already in 0-100 range)
        iv_rank = item.get("implied-volatility-index-rank")
        if iv_rank is not None:
            try:
                metrics["iv_rank"] = float(iv_rank)
            except (ValueError, TypeError):
                pass

        iv_percentile = item.get("implied-volatility-percentile")
        if iv_percentile is not None:
            try:
                metrics["iv_percentile"] = float(iv_percentile)
            except (ValueError, TypeError):
                pass

        # Liquidity metrics
        liquidity_rating = item.get("liquidity-rating")
        if liquidity_rating is not None:
            try:
                metrics["liquidity_rating"] = int(liquidity_rating)
            except (ValueError, TypeError):
                pass

        liquidity_value = item.get("liquidity-value")
        if liquidity_value is not None:
            try:
                metrics["liquidity_value"] = float(liquidity_value)
            except (ValueError, TypeError):
                pass

        # Correlation
        corr_spy = item.get("corr-spy-3month")
        if corr_spy is not None:
            try:
                metrics["corr_spy_3month"] = float(corr_spy)
            except (ValueError, TypeError):
                pass

        # Beta
        beta = item.get("beta")
        if beta is not None:
            try:
                metrics["beta"] = float(beta)
            except (ValueError, TypeError):
                pass

        # Earnings
        earnings = item.get("earnings", {})
        if isinstance(earnings, dict):
            earnings_date = earnings.get("expected-report-date")
            if earnings_date:
                metrics["earnings_date"] = str(earnings_date)

        # Metadata
        updated_at = item.get("updated-at")
        if updated_at:
            metrics["updated_at"] = str(updated_at)

        return metrics

    def _fetch_api_data(
        self, url: str, headers: dict[str, str], params: dict[str, str]
    ) -> Optional[Any]:
        """
        Fetch data from Tastytrade API with error handling.

        Args:
            url: API endpoint URL
            headers: HTTP headers including auth token
            params: Query parameters

        Returns:
            JSON response as dict, or None if error
        """
        try:
            response = requests.get(url, headers=headers, params=params, timeout=15)

            # Handle common HTTP errors
            if response.status_code == 401:
                # Token may have expired prematurely, try once more
                self._access_token = None
                token = self._ensure_valid_token()
                headers["Authorization"] = f"Bearer {token}"
                response = requests.get(url, headers=headers, params=params, timeout=15)

            if response.status_code == 404:
                return None

            if response.status_code == 429:
                raise requests.exceptions.RequestException(
                    "Rate limit exceeded. Retry after delay."
                )

            if response.status_code >= 500:
                raise requests.exceptions.RequestException(
                    f"Tastytrade server error: {response.status_code}"
                )

            response.raise_for_status()
            return response.json()

        except (requests.exceptions.RequestException, ValueError) as e:
            print(f"Tastytrade API error: {e}")
            return None

    def get_market_metrics(self, symbols: list[str]) -> dict[str, TastytradeMetrics]:
        """
        Fetch market metrics for a list of symbols from Tastytrade API.

        This method:
        1. Ensures valid OAuth token
        2. Queries /market-metrics endpoint with comma-separated symbols
        3. Converts IV from decimal to percent (*100)
        4. Maps Tastytrade response fields to TastytradeMetrics format

        Args:
            symbols: List of ticker symbols (e.g., ['AAPL', 'SPY', 'QQQ'])

        Returns:
            Dictionary mapping symbols to their metrics.
            Symbols with errors will have empty/partial data.

        Raises:
            TastytradeAuthError: If authentication fails
            requests.exceptions.RequestException: If API request fails

        Example:
            >>> client = TastytradeClient()
            >>> metrics = client.get_market_metrics(['AAPL', 'SPY'])
            >>> print(metrics['AAPL']['iv'])
            35.4  # Already converted to percent
        """
        if not symbols:
            return {}

        # Ensure valid authentication
        token = self._ensure_valid_token()

        # Build request
        symbols_str = ",".join(symbols)
        url = f"{self.api_base_url}/market-metrics"
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }
        params = {"symbols": symbols_str}

        # Fetch data from API
        data = self._fetch_api_data(url, headers, params)
        if not data:
            return {}

        # Extract items from response
        items = data.get("data", {}).get("items", []) if isinstance(data, dict) else []
        if not items and isinstance(data, list):
            items = data

        # Parse each item
        results: dict[str, TastytradeMetrics] = {}
        for item in items:
            metrics = self._parse_metric_item(item)
            if metrics and "symbol" in metrics:
                results[metrics["symbol"]] = metrics

        return results
