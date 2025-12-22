import pytest

from portfolio_parser import parse_currency, parse_dte, get_root_symbol


def test_parse_currency_handles_broker_formats():
    assert parse_currency('$1,234.56') == 1234.56
    assert parse_currency('(500)') == -500.0


def test_parse_dte_ignores_suffix_noise():
    assert parse_dte('45 DTE') == 45
    assert parse_dte('10 days') == 10


def test_get_root_symbol_normalizes_class_shares():
    assert get_root_symbol('BRK/B') == 'BRK-B'
    assert get_root_symbol('ETH/USD') == 'ETH-USD'


@pytest.mark.xfail(reason='Futures year codes beyond 2 digits are not normalized.')
def test_get_root_symbol_long_year_code():
    assert get_root_symbol('/ESZ2024') == '/ES'
