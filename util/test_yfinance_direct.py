import yfinance as yf
import sys

def test_single_symbol(symbol):
    print(f"Testing direct yfinance access for {symbol}...")
    try:
        ticker = yf.Ticker(symbol)
        
        # Test fast_info
        try:
            fast_price = ticker.fast_info.last_price
            print(f"  fast_info.last_price: {fast_price}")
        except Exception as e:
            print(f"  fast_info failed: {e}")

        # Test history
        try:
            hist = ticker.history(period="1d", interval="1m")
            if not hist.empty:
                print(f"  history last close: {hist['Close'].iloc[-1]}")
            else:
                print(f"  history empty: {hist}")
        except Exception as e:
            print(f"  history failed: {e}")
            
        # Test info (as a last resort to see if any price comes)
        try:
            info_price = ticker.info.get('regularMarketPrice')
            print(f"  info.regularMarketPrice: {info_price}")
        except Exception as e:
            print(f"  info failed: {e}")

    except Exception as e:
        print(f"  General error for {symbol}: {e}")

if __name__ == "__main__":
    test_single_symbol("SPY")
    test_single_symbol("TSLA")
