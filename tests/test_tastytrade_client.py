import time

import pytest
import requests

from variance import tastytrade_client as tt


class DummyResponse:
    def __init__(self, status_code, json_data=None, raise_for_status_exc=None):
        self.status_code = status_code
        self._json_data = json_data
        self._raise_for_status_exc = raise_for_status_exc

    def json(self):
        if isinstance(self._json_data, Exception):
            raise self._json_data
        return self._json_data

    def raise_for_status(self):
        if self._raise_for_status_exc:
            raise self._raise_for_status_exc
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"{self.status_code}")


@pytest.fixture
def tastytrade_env(monkeypatch):
    monkeypatch.setenv("TT_CLIENT_ID", "client-id")
    monkeypatch.setenv("TT_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("TT_REFRESH_TOKEN", "refresh-token")
    monkeypatch.setenv("API_BASE_URL", "https://api.tastytrade.com")


def test_init_missing_env_raises(monkeypatch):
    monkeypatch.delenv("TT_CLIENT_ID", raising=False)
    monkeypatch.delenv("TT_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("TT_REFRESH_TOKEN", raising=False)

    with pytest.raises(tt.TastytradeAuthError) as exc:
        tt.TastytradeClient()

    message = str(exc.value)
    assert "TT_CLIENT_ID" in message
    assert "TT_CLIENT_SECRET" in message
    assert "TT_REFRESH_TOKEN" in message


def test_refresh_access_token_success(monkeypatch, tastytrade_env):
    client = tt.TastytradeClient()

    def fake_post(url, json, timeout):
        assert url.endswith("/oauth/token")
        return DummyResponse(200, {"access_token": "token-123", "expires_in": 120})

    monkeypatch.setattr(tt.requests, "post", fake_post)
    before = time.time()
    client._refresh_access_token()

    assert client._access_token == "token-123"
    assert client._token_expiry > before


def test_refresh_access_token_invalid_response(monkeypatch, tastytrade_env):
    client = tt.TastytradeClient()

    def fake_post(url, json, timeout):
        return DummyResponse(200, {"expires_in": 120})

    monkeypatch.setattr(tt.requests, "post", fake_post)

    with pytest.raises(tt.TastytradeAuthError):
        client._refresh_access_token()


def test_ensure_valid_token_refreshes(monkeypatch, tastytrade_env):
    client = tt.TastytradeClient()
    client._access_token = None
    client._token_expiry = 0.0

    def fake_refresh():
        client._access_token = "fresh-token"
        client._token_expiry = time.time() + 120

    monkeypatch.setattr(client, "_refresh_access_token", fake_refresh)
    assert client._ensure_valid_token() == "fresh-token"


def test_parse_metric_item_scales_and_normalizes(tastytrade_env):
    client = tt.TastytradeClient()
    item = {
        "symbol": "aapl",
        "historical-volatility-30-day": "20.0",
        "historical-volatility-90-day": 25.0,
        "implied-volatility-index": 0.4,
        "implied-volatility-index-rank": "45",
        "implied-volatility-percentile": 0.75,
        "liquidity-rating": "4",
        "liquidity-value": "12.5",
        "corr-spy-3month": "0.82",
        "beta": "1.1",
        "earnings": {"expected-report-date": "2024-12-01"},
        "updated-at": "2024-11-01T00:00:00Z",
    }

    metrics = client._parse_metric_item(item)
    assert metrics is not None
    assert metrics["symbol"] == "AAPL"
    assert metrics["iv"] == 40.0
    assert metrics["iv_rank"] == 45.0
    assert metrics["iv_percentile"] == 75.0
    assert metrics["liquidity_rating"] == 4
    assert metrics["liquidity_value"] == 12.5
    assert metrics["corr_spy_3month"] == 0.82
    assert metrics["beta"] == 1.1
    assert metrics["earnings_date"] == "2024-12-01"
    assert metrics["updated_at"] == "2024-11-01T00:00:00Z"


def test_fetch_api_data_retries_on_401(monkeypatch, tastytrade_env):
    client = tt.TastytradeClient()
    client._access_token = "old-token"
    client._token_expiry = time.time() + 120

    calls = []

    def fake_get(url, headers, params, timeout):
        calls.append(headers["Authorization"])
        if len(calls) == 1:
            return DummyResponse(401, {"error": "expired"})
        return DummyResponse(200, {"data": {"items": [{"symbol": "AAPL"}]}})

    monkeypatch.setattr(tt.requests, "get", fake_get)
    monkeypatch.setattr(client, "_ensure_valid_token", lambda: "new-token")

    data = client._fetch_api_data(
        "https://api.tastytrade.com/market-metrics",
        {"Authorization": "Bearer old-token"},
        {"symbols": "AAPL"},
    )

    assert data == {"data": {"items": [{"symbol": "AAPL"}]}}
    assert calls == ["Bearer old-token", "Bearer new-token"]


def test_fetch_api_data_handles_errors(monkeypatch, tastytrade_env):
    client = tt.TastytradeClient()

    def fake_get_404(url, headers, params, timeout):
        return DummyResponse(404, {"error": "not found"})

    monkeypatch.setattr(tt.requests, "get", fake_get_404)
    assert (
        client._fetch_api_data(
            "https://api.tastytrade.com/market-metrics", {"Authorization": "Bearer x"}, {}
        )
        is None
    )

    def fake_get_429(url, headers, params, timeout):
        return DummyResponse(429, {"error": "rate limit"})

    monkeypatch.setattr(tt.requests, "get", fake_get_429)
    assert (
        client._fetch_api_data(
            "https://api.tastytrade.com/market-metrics", {"Authorization": "Bearer x"}, {}
        )
        is None
    )

    def fake_get_500(url, headers, params, timeout):
        return DummyResponse(500, {"error": "server"})

    monkeypatch.setattr(tt.requests, "get", fake_get_500)
    assert (
        client._fetch_api_data(
            "https://api.tastytrade.com/market-metrics", {"Authorization": "Bearer x"}, {}
        )
        is None
    )


def test_get_market_metrics_parses_items(monkeypatch, tastytrade_env):
    client = tt.TastytradeClient()

    monkeypatch.setattr(client, "_ensure_valid_token", lambda: "token")
    monkeypatch.setattr(
        client,
        "_fetch_api_data",
        lambda url, headers, params: {
            "data": {"items": [{"symbol": "AAPL", "implied-volatility-index": 0.2}]}
        },
    )

    results = client.get_market_metrics(["AAPL"])
    assert "AAPL" in results
    assert results["AAPL"]["iv"] == 20.0


def test_get_market_metrics_accepts_list_response(monkeypatch, tastytrade_env):
    client = tt.TastytradeClient()

    monkeypatch.setattr(client, "_ensure_valid_token", lambda: "token")
    monkeypatch.setattr(
        client,
        "_fetch_api_data",
        lambda url, headers, params: [{"symbol": "MSFT", "implied-volatility-index": 25.0}],
    )

    results = client.get_market_metrics(["MSFT"])
    assert results["MSFT"]["iv"] == 25.0
