"""
QA Validation Tests for ETF Sector Handling Fix
Tests the safe_get_sector() function and SECTOR_OVERRIDES configuration
"""

import sys
from unittest.mock import Mock, PropertyMock, patch

from variance import get_market_data


def test_sector_override_priority():
    """SECTOR_OVERRIDES should take priority over API calls"""
    ticker_mock = Mock()
    # Even if ticker.info would work, override should win
    ticker_mock.info = {"sector": "ShouldNotSee"}

    # Test with XME which is in SECTOR_OVERRIDES
    result = get_market_data.safe_get_sector(ticker_mock, "XME", "XME")
    assert result == "Materials", f"Expected 'Materials', got '{result}'"


def test_http_404_error_suppression():
    """HTTP 404 errors should be silently handled and return 'Unknown'"""
    ticker_mock = Mock()
    # Simulate yfinance raising an exception when accessing .info
    type(ticker_mock).info = PropertyMock(side_effect=Exception("HTTP Error 404: Not Found"))

    # Clear cache to ensure fresh fetch
    with patch.object(get_market_data.cache, "get", return_value=None):
        result = get_market_data.safe_get_sector(ticker_mock, "FAKE_ETF", "FAKE_ETF")

    assert result == "Unknown", f"Expected 'Unknown', got '{result}'"


def test_no_stderr_output_on_error(capsys):
    """HTTP errors should not pollute stderr"""
    ticker_mock = Mock()

    def raise_and_print():
        # Simulate what yfinance does - prints to stderr then raises
        print("HTTP Error 404: quoteSummary Not Found", file=sys.stderr)
        raise Exception("404")

    type(ticker_mock).info = PropertyMock(side_effect=raise_and_print)

    with patch.object(get_market_data.cache, "get", return_value=None):
        result = get_market_data.safe_get_sector(ticker_mock, "FAKE_ETF", "FAKE_ETF")

    captured = capsys.readouterr()
    # The stderr redirect should suppress the error message
    assert "HTTP Error 404" not in captured.err, "HTTP error should be suppressed"
    assert result == "Unknown"


def test_etf_sector_overrides_exist():
    """Critical ETF symbols should have sector overrides"""
    critical_etfs = {
        "XME": "Materials",
        "HYG": "Fixed Income",
        "XOP": "Energy",
        "CPER": "Metals",
    }

    for symbol, expected_sector in critical_etfs.items():
        assert symbol in get_market_data.SECTOR_OVERRIDES, f"{symbol} missing from SECTOR_OVERRIDES"
        actual_sector = get_market_data.SECTOR_OVERRIDES[symbol]
        assert actual_sector == expected_sector, (
            f"{symbol}: expected '{expected_sector}', got '{actual_sector}'"
        )


def test_safe_get_sector_unknown_fallback():
    """Unknown symbols should return 'Unknown' without errors"""
    ticker_mock = Mock()
    ticker_mock.info = {}  # Empty info (no sector key)

    with patch.object(get_market_data.cache, "get", return_value=None):
        result = get_market_data.safe_get_sector(ticker_mock, "UNKNOWN_SYM", "UNKNOWN_SYM")

    assert result == "Unknown"


if __name__ == "__main__":
    print("Running ETF Sector Handling QA Tests...")

    # Test 1: Sector Override Priority
    try:
        test_sector_override_priority()
        print("✅ PASS: Sector override priority test")
    except AssertionError as e:
        print(f"❌ FAIL: Sector override priority test - {e}")

    # Test 2: HTTP 404 Error Suppression
    try:
        test_http_404_error_suppression()
        print("✅ PASS: HTTP 404 error suppression test")
    except AssertionError as e:
        print(f"❌ FAIL: HTTP 404 error suppression test - {e}")

    # Test 3: ETF Sector Overrides Exist
    try:
        test_etf_sector_overrides_exist()
        print("✅ PASS: ETF sector overrides exist test")
    except AssertionError as e:
        print(f"❌ FAIL: ETF sector overrides exist test - {e}")

    # Test 4: Unknown Fallback
    try:
        test_safe_get_sector_unknown_fallback()
        print("✅ PASS: Unknown fallback test")
    except AssertionError as e:
        print(f"❌ FAIL: Unknown fallback test - {e}")

    print("\n🎯 QA Validation Complete")
