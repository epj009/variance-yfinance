"""
Variance Systematic Volatility Engine
"""

# 1. Initialize Registry Patterns (force decorator execution)
from .strategies import factory as _  # noqa: F401
from .triage import handlers as _  # noqa: F401

# 2. Export Public API
from .analyze_portfolio import analyze_portfolio
from .get_market_data import get_market_data
from .vol_screener import screen_volatility

__version__ = "0.1.0"
