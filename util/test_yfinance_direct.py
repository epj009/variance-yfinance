import pytest
import yfinance as yf
import sys

# This is a manual connectivity helper, not a unit test; skip under pytest collection
pytestmark = pytest.mark.skip("network helper (not a unit test)")

def test_single_symbol(symbol):
    """
    Perform a minimal test of yfinance data fetching for a single symbol.
    
    Retrieves the Ticker object and prints the 'fast_info' price.
    Useful for quick connectivity checks.
    """
    print(f"Testing {symbol}...")
    t = yf.Ticker(symbol)
    try:
        print(f"Price: {t.fast_info.last_price}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    target = "SPY"
    if len(sys.argv) > 1:
        target = sys.argv[1]
    test_single_symbol(target)
