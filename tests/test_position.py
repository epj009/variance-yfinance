"""
Unit tests for Position Domain Object.

Tests the Position dataclass encapsulating individual position legs
with validated data access and property methods.
"""

import pytest

from variance.models import Position


class TestPositionFromRow:
    """Test Position.from_row() factory method."""

    def test_from_row_creates_position_with_valid_data(self):
        """Happy path: Create Position from complete option leg data."""
        row = {
            "Symbol": "AAPL 250117P150",
            "Type": "Option",
            "Call/Put": "Put",
            "Quantity": "-1.0",
            "Strike Price": "150.0",
            "Exp Date": "2025-01-17",
            "DTE": "45",
            "Cost": "-100.0",
            "P/L Open": "50.0",
            "Delta": "10.0",
            "beta_delta": "10.5",
            "Theta": "-2.0",
            "Gamma": "0.05",
            "Vega": "5.0",
            "Bid": "1.00",
            "Ask": "1.10",
            "Mark": "1.05",
            "Underlying Last Price": "155.0",
        }

        position = Position.from_row(row)

        assert position.symbol == "AAPL 250117P150"
        assert position.asset_type == "Option"
        assert position.quantity == -1.0
        assert position.strike == 150.0
        assert position.dte == 45
        assert position.exp_date == "2025-01-17"
        assert position.call_put == "Put"
        assert position.underlying_price == 155.0
        assert position.pl_open == 50.0
        assert position.cost == -100.0
        assert position.delta == 10.0
        assert position.beta_delta == 10.5
        assert position.theta == -2.0
        assert position.gamma == 0.05
        assert position.vega == 5.0
        assert position.bid == 1.00
        assert position.ask == 1.10
        assert position.mark == 1.05
        assert position.raw_data == row

    def test_from_row_handles_missing_optional_fields(self):
        """Minimal required fields: Missing optional fields should use defaults."""
        row = {
            "Symbol": "SPY",
            "Type": "Stock",
            "Quantity": "100",
        }

        position = Position.from_row(row)

        assert position.symbol == "SPY"
        assert position.asset_type == "Stock"
        assert position.quantity == 100.0
        assert position.strike is None
        assert position.dte == 0
        assert position.exp_date is None
        assert position.call_put is None
        assert position.underlying_price == 0.0
        assert position.pl_open == 0.0
        assert position.cost == 0.0

    def test_from_row_with_none_strike_for_stock(self):
        """Stock positions have no strike price."""
        row = {
            "Symbol": "QQQ",
            "Type": "Stock",
            "Quantity": "50",
            "Strike Price": None,
        }

        position = Position.from_row(row)

        assert position.asset_type == "Stock"
        assert position.strike is None

    def test_from_row_with_malformed_numeric_values(self):
        """Parse currency should handle 'N/A' and malformed values."""
        row = {
            "Symbol": "TEST",
            "Type": "Option",
            "Quantity": "N/A",
            "Strike Price": "--",
            "DTE": "abc",
            "Cost": "",
            "P/L Open": "invalid",
        }

        position = Position.from_row(row)

        assert position.quantity == 0.0
        assert position.strike is None
        assert position.dte == 0
        assert position.cost == 0.0
        assert position.pl_open == 0.0


class TestPositionRootSymbol:
    """Test Position.root_symbol property."""

    def test_root_symbol_property_for_equity(self):
        """Extract root symbol from equity option symbol."""
        position = Position(
            symbol="AAPL 250117P150",
            asset_type="Option",
            quantity=-1.0,
        )

        assert position.root_symbol == "AAPL"

    def test_root_symbol_property_for_futures(self):
        """Extract root symbol from futures symbol."""
        position = Position(
            symbol="/ESZ24",
            asset_type="Future",
            quantity=1.0,
        )

        assert position.root_symbol == "/ES"

    def test_root_symbol_property_for_micro_futures(self):
        """Extract root symbol from micro futures symbol."""
        position = Position(
            symbol="/MESZ4",
            asset_type="Future",
            quantity=1.0,
        )

        assert position.root_symbol == "/MES"


class TestPositionTypeProperties:
    """Test Position type detection properties."""

    def test_is_option_property_returns_true_for_options(self):
        """Position with asset_type='Option' should be is_option=True."""
        position = Position(
            symbol="SPY 250117C500",
            asset_type="Option",
            quantity=-1.0,
        )

        assert position.is_option is True
        assert position.is_stock is False

    def test_is_stock_property_returns_true_for_stock(self):
        """Position with asset_type='Stock' should be is_stock=True."""
        position = Position(
            symbol="AAPL",
            asset_type="Stock",
            quantity=100.0,
        )

        assert position.is_stock is True
        assert position.is_option is False


class TestPositionDirectionProperties:
    """Test Position direction detection properties."""

    def test_is_short_property_identifies_negative_quantity(self):
        """Position with quantity < 0 should be is_short=True."""
        position = Position(
            symbol="TEST",
            asset_type="Option",
            quantity=-2.0,
        )

        assert position.is_short is True
        assert position.is_long is False

    def test_is_long_property_identifies_positive_quantity(self):
        """Position with quantity > 0 should be is_long=True."""
        position = Position(
            symbol="TEST",
            asset_type="Option",
            quantity=3.0,
        )

        assert position.is_long is True
        assert position.is_short is False


class TestPositionImmutability:
    """Test Position immutability (frozen dataclass)."""

    def test_position_immutability(self):
        """Frozen dataclass should prevent modification."""
        position = Position(
            symbol="TEST",
            asset_type="Option",
            quantity=-1.0,
        )

        with pytest.raises(AttributeError):
            position.quantity = 5.0
