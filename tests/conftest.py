"""
Shared pytest fixtures for test suite.
"""

from datetime import datetime
from unittest.mock import Mock

import numpy as np
import pandas as pd
import pytest

from variance import get_market_data
from variance.interfaces import IMarketDataProvider, MarketData


class MockMarketDataProvider(IMarketDataProvider):
    """Fake provider for testing."""
    def __init__(self, data: dict):
        self.data = data

    def get_market_data(self, symbols: list[str]) -> dict[str, MarketData]:
        return {s: self.data[s] for s in symbols if s in self.data}

    def get_current_price(self, symbol: str) -> float:
        if symbol in self.data:
            return self.data[symbol].get('price', 0.0)
        return 0.0

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
    - Monkeypatches get_market_data.DB_PATH
    - Replaces get_market_data.cache with fresh MarketCache instance
    - Cleans up after test

    Returns:
        pathlib.Path: Path to temporary database file
    """
    db_path = tmp_path / "test_cache.db"

    # Patch module-level DB_PATH
    monkeypatch.setattr(get_market_data, 'DB_PATH', str(db_path))

    # Create fresh cache instance
    fresh_cache = get_market_data.MarketCache(str(db_path))
    monkeypatch.setattr(get_market_data, 'cache', fresh_cache)

    return db_path


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
    calls = pd.DataFrame({
        'strike': [145.0, 147.5, 150.0, 152.5, 155.0],
        'bid': [6.20, 4.50, 3.10, 1.90, 1.05],
        'ask': [6.40, 4.70, 3.25, 2.05, 1.15],
        'impliedVolatility': [0.32, 0.30, 0.28, 0.29, 0.31],
        'openInterest': [4200, 6100, 9800, 5300, 3200],
        'volume': [1250, 2100, 5600, 1800, 950],
        'dist': [5.0, 2.5, 0.0, 2.5, 5.0]  # Distance from ATM
    })

    puts = pd.DataFrame({
        'strike': [145.0, 147.5, 150.0, 152.5, 155.0],
        'bid': [1.10, 1.85, 3.00, 4.40, 6.10],
        'ask': [1.20, 2.00, 3.15, 4.55, 6.30],
        'impliedVolatility': [0.31, 0.29, 0.28, 0.30, 0.32],
        'openInterest': [3800, 5900, 10100, 5600, 3400],
        'volume': [980, 1500, 5200, 1650, 1100],
        'dist': [5.0, 2.5, 0.0, 2.5, 5.0]
    })

    return calls, puts


@pytest.fixture
def mock_ticker_factory():
    """
    Factory fixture that creates mock yfinance Ticker objects with configurable behavior.

    Usage:
        ticker = mock_ticker_factory(
            symbol="AAPL",
            price=150.0,
            history_data=pd.DataFrame(...),
            options=["2025-01-17", "2025-02-21"],
            option_chain_calls=pd.DataFrame(...),
            option_chain_puts=pd.DataFrame(...),
            info={"sector": "Technology"},
            calendar=pd.DataFrame(...),
        )

    Returns:
        Mock: Configured yfinance.Ticker mock object
    """
    def _create_ticker(
        symbol: str = "TEST",
        price: float = 100.0,
        history_data: pd.DataFrame = None,
        options: list = None,
        option_chain_calls: pd.DataFrame = None,
        option_chain_puts: pd.DataFrame = None,
        info: dict = None,
        calendar: pd.DataFrame = None
    ):
        mock = Mock()

        # fast_info property
        mock.fast_info = Mock()
        mock.fast_info.last_price = price

        # history() method
        if history_data is None:
            # Generate 252 days of dummy price data
            dates = pd.date_range(end=datetime.now(), periods=252, freq='D')
            history_data = pd.DataFrame({
                'Close': np.random.normal(price, price * 0.02, 252)
            }, index=dates)
        mock.history.return_value = history_data

        # options property
        mock.options = options if options is not None else ["2025-02-15"]

        # option_chain() method
        def _option_chain(exp_date):
            chain = Mock()
            chain.calls = option_chain_calls if option_chain_calls is not None else pd.DataFrame()
            chain.puts = option_chain_puts if option_chain_puts is not None else pd.DataFrame()
            return chain
        mock.option_chain = _option_chain

        # info property
        mock.info = info if info is not None else {"sector": "Technology"}

        # calendar property
        mock.calendar = calendar if calendar is not None else pd.DataFrame()

        return mock

    return _create_ticker


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
            "require_portfolio_long": True
        }
    }


@pytest.fixture
def mock_market_config():
    """Market configuration for friction calculations."""
    return {
        "FUTURES_MULTIPLIERS": {
            "/ES": 50,
            "/CL": 1000,
            "/GC": 100
        }
    }


@pytest.fixture
def mock_strategies():
    """Strategy configs with profit target overrides."""
    return {
        "short_strangle": {
            "management": {"profit_target_pct": 0.50},
            "metadata": {"gamma_trigger_dte": 21}
        },
        "iron_condor": {
            "management": {"profit_target_pct": 0.50},
            "metadata": {"gamma_trigger_dte": 21}
        }
    }


@pytest.fixture
def make_option_leg():
    """Factory for creating normalized option leg dictionaries."""
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
        theta: float = -2.0,
        gamma: float = 0.05,
        bid: float = 1.00,
        ask: float = 1.10,
        underlying_price: float = 155.0
    ) -> dict:
        return {
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
            "Theta": str(theta),
            "Gamma": str(gamma),
            "Bid": str(bid),
            "Ask": str(ask),
            "Underlying Last Price": str(underlying_price),
            "Mark": str((bid + ask) / 2)
        }
    return _make


@pytest.fixture
def make_triage_context(mock_trading_rules, mock_market_config, mock_strategies):
    """Factory for creating TriageContext objects."""
    def _make(
        market_data: dict = None,
        rules: dict = None,
        portfolio_beta_delta: float = 50.0,
        traffic_jam_friction: float = 999.0
    ):
        return {
            "market_data": market_data or {},
            "rules": rules or mock_trading_rules,
            "market_config": mock_market_config,
            "strategies": mock_strategies,
            "traffic_jam_friction": traffic_jam_friction,
            "portfolio_beta_delta": portfolio_beta_delta
        }
    return _make
