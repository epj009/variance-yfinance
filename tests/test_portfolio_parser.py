"""
Unit tests for portfolio_parser module.
"""

import pytest
import sys
import os

# Add scripts directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from portfolio_parser import parse_currency, parse_dte, get_root_symbol, is_stock_type


class TestParseCurrency:
    """Test currency parsing utility."""

    def test_parse_currency_handles_commas(self):
        assert parse_currency("$1,234.56") == 1234.56

    def test_parse_currency_handles_negative(self):
        assert parse_currency("-$500.00") == -500.0

    def test_parse_currency_handles_percent(self):
        assert parse_currency("50%") == 50.0

    def test_parse_currency_handles_dash(self):
        assert parse_currency("--") == 0.0

    def test_parse_currency_handles_none(self):
        assert parse_currency(None) == 0.0

    def test_parse_currency_handles_invalid(self):
        assert parse_currency("abc") == 0.0


class TestParseDTE:
    """Test DTE parsing utility."""

    def test_parse_dte_strips_suffix(self):
        assert parse_dte("45d") == 45

    def test_parse_dte_handles_plain_number(self):
        assert parse_dte("30") == 30

    def test_parse_dte_handles_none(self):
        assert parse_dte(None) == 0

    def test_parse_dte_handles_invalid(self):
        assert parse_dte("abc") == 0


class TestGetRootSymbol:
    """Test root symbol extraction."""

    def test_get_root_symbol_futures_standard(self):
        assert get_root_symbol("/ESZ24") == "/ES"

    def test_get_root_symbol_futures_with_dot(self):
        assert get_root_symbol("./CLG6") == "/CL"

    def test_get_root_symbol_micro_futures(self):
        assert get_root_symbol("/MESZ4") == "/MES"
        assert get_root_symbol("/MNQH25") == "/MNQ"
        assert get_root_symbol("/M2KZ4") == "/M2K"
        assert get_root_symbol("/SR3Z4") == "/SR3"

    def test_get_root_symbol_equity(self):
        assert get_root_symbol("AAPL") == "AAPL"

    def test_get_root_symbol_with_spaces(self):
        assert get_root_symbol("SPY  100C") == "SPY"

    def test_get_root_symbol_handles_none(self):
        assert get_root_symbol(None) == ""

    def test_get_root_symbol_handles_empty(self):
        assert get_root_symbol("") == ""


class TestIsStockType:
    """Test stock type detection."""

    def test_is_stock_type_stock(self):
        assert is_stock_type("Stock") is True

    def test_is_stock_type_equity(self):
        assert is_stock_type("Equity") is True

    def test_is_stock_type_case_insensitive(self):
        assert is_stock_type("STOCK") is True
        assert is_stock_type("equity") is True

    def test_is_stock_type_option(self):
        assert is_stock_type("Call") is False
        assert is_stock_type("Put") is False

    def test_is_stock_type_none(self):
        assert is_stock_type(None) is False
