"""
Shared pytest fixtures for test suite.
"""

import importlib

import pandas as pd
import pytest

from variance.interfaces import IMarketDataProvider, MarketData
from variance.market_data import settings as md_settings
from variance.market_data.cache import MarketCache
from variance.models import Position


class MockMarketDataProvider(IMarketDataProvider):
    """Fake provider for testing."""

    def __init__(self, data: dict):
        self.data = data

    def get_market_data(
        self,
        symbols: list[str],
        *,
        include_returns: bool = False,
        include_option_quotes: bool = False,
    ) -> dict[str, MarketData]:
        return {s: self.data[s] for s in symbols if s in self.data}


@pytest.fixture
def mock_market_provider():
    """Returns a factory function to create a provider with specific data."""

    def _create(data):
        return MockMarketDataProvider(data)

    return _create


@pytest.fixture
def temp_cache_db(tmp_path, monkeypatch):
    """
    Creates isolated SQLite cache database per test.

    - Creates temp .db file in tmp_path
    - Monkeypatches market_data.settings.DB_PATH
    - Replaces default cache instances with a fresh MarketCache
    - Cleans up after test

    Returns:
        pathlib.Path: Path to temporary database file
    """
    db_path = tmp_path / "test_cache.db"

    # Patch module-level DB_PATH
    monkeypatch.setattr(md_settings, "DB_PATH", str(db_path))

    fresh_cache = MarketCache(str(db_path))
    cache_mod = importlib.import_module("variance.market_data.cache")
    pure_mod = importlib.import_module("variance.market_data.pure_tastytrade_provider")
    service_mod = importlib.import_module("variance.market_data.service")

    monkeypatch.setattr(cache_mod, "cache", fresh_cache)
    monkeypatch.setattr(pure_mod, "cache", fresh_cache)
    monkeypatch.setattr(service_mod, "default_cache", fresh_cache)

    yield db_path

    # Explicit cleanup to prevent ResourceWarning
    try:
        fresh_cache.close_all()
    except Exception:
        pass  # Already closed or doesn't exist


@pytest.fixture
def mock_option_chain():
    """
    Returns realistic option chain DataFrames for testing.

    Returns:
        Tuple[pd.DataFrame, pd.DataFrame]: (calls_df, puts_df)

    DataFrame schema:
        - strike: float
        - bid: float
        - ask: float
        - impliedVolatility: float (0.0 to 1.0 range)
        - volume: int
    """
    calls = pd.DataFrame(
        {
            "strike": [145.0, 147.5, 150.0, 152.5, 155.0],
            "bid": [6.20, 4.50, 3.10, 1.90, 1.05],
            "ask": [6.40, 4.70, 3.25, 2.05, 1.15],
            "impliedVolatility": [0.32, 0.30, 0.28, 0.29, 0.31],
            "openInterest": [4200, 6100, 9800, 5300, 3200],
            "volume": [1250, 2100, 5600, 1800, 950],
            "dist": [5.0, 2.5, 0.0, 2.5, 5.0],  # Distance from ATM
        }
    )

    puts = pd.DataFrame(
        {
            "strike": [145.0, 147.5, 150.0, 152.5, 155.0],
            "bid": [1.10, 1.85, 3.00, 4.40, 6.10],
            "ask": [1.20, 2.00, 3.15, 4.55, 6.30],
            "impliedVolatility": [0.31, 0.29, 0.28, 0.30, 0.32],
            "openInterest": [3800, 5900, 10100, 5600, 3400],
            "volume": [980, 1500, 5200, 1650, 1100],
            "dist": [5.0, 2.5, 0.0, 2.5, 5.0],
        }
    )

    return calls, puts


@pytest.fixture
def mock_trading_rules():
    """Standard trading rules for triage tests - all config-driven."""
    return {
        "vrp_structural_threshold": 0.85,
        "dead_money_vrp_structural_threshold": 0.80,
        "dead_money_pl_pct_low": -0.10,
        "dead_money_pl_pct_high": 0.10,
        "low_ivr_threshold": 20,
        "gamma_dte_threshold": 21,
        "profit_harvest_pct": 0.50,
        "earnings_days_threshold": 5,
        "concentration_limit_pct": 0.05,
        "max_strategies_per_symbol": 3,
        "hedge_rules": {
            "enabled": True,
            "index_symbols": ["SPY", "QQQ", "IWM"],
            "qualifying_strategies": ["Long Put", "Vertical Spread (Put)"],
            "delta_threshold": -5,
            "require_portfolio_long": True,
        },
    }


@pytest.fixture
def mock_market_config():
    """Market configuration for friction calculations."""
    return {"FUTURES_MULTIPLIERS": {"/ES": 50, "/CL": 1000, "/GC": 100}}


@pytest.fixture
def mock_strategies():
    """Strategy configs with profit target overrides."""
    return {
        "short_strangle": {
            "management": {"profit_target_pct": 0.50},
            "metadata": {"gamma_trigger_dte": 21},
        },
        "iron_condor": {
            "management": {"profit_target_pct": 0.50},
            "metadata": {"gamma_trigger_dte": 21},
        },
    }


@pytest.fixture
def make_option_leg():
    """Factory for creating normalized option leg positions."""

    def _make(
        symbol: str = "AAPL",
        call_put: str = "Put",
        quantity: int = -1,
        strike: float = 150.0,
        dte: int = 45,
        cost: float = -100.0,
        pl_open: float = 50.0,
        delta: float = 10.0,
        beta_delta: float = 10.0,
        beta_gamma: float | None = None,
        theta: float = -2.0,
        gamma: float = 0.05,
        bid: float = 1.00,
        ask: float = 1.10,
        underlying_price: float = 155.0,
    ):
        row = {
            "Symbol": f"{symbol} 250117P{int(strike)}",
            "Type": "Option",
            "Call/Put": call_put,
            "Quantity": str(quantity),
            "Strike Price": str(strike),
            "Exp Date": "2025-01-17",
            "DTE": str(dte),
            "Cost": str(cost),
            "P/L Open": str(pl_open),
            "Delta": str(delta),
            "beta_delta": str(beta_delta),
            "beta_gamma": "" if beta_gamma is None else str(beta_gamma),
            "Theta": str(theta),
            "Gamma": str(gamma),
            "Bid": str(bid),
            "Ask": str(ask),
            "Underlying Last Price": str(underlying_price),
            "Mark": str((bid + ask) / 2),
        }
        return Position.from_row(row)

    return _make


@pytest.fixture
def make_triage_context(mock_trading_rules, mock_market_config, mock_strategies):
    """Factory for creating TriageContext objects."""

    def _make(
        market_data: dict = None,
        rules: dict = None,
        portfolio_beta_delta: float = 50.0,
        traffic_jam_friction: float = 999.0,
    ):
        return {
            "market_data": market_data or {},
            "rules": rules or mock_trading_rules,
            "market_config": mock_market_config,
            "strategies": mock_strategies,
            "traffic_jam_friction": traffic_jam_friction,
            "portfolio_beta_delta": portfolio_beta_delta,
        }

    return _make
