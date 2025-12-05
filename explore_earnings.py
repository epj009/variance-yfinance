import yfinance as yf
import sys

def check_earnings(symbol):
    print(f"Checking {symbol}...")
    t = yf.Ticker(symbol)
    
    print("--- calendar ---")
    try:
        cal = t.calendar
        print(cal)
    except Exception as e:
        print(f"Calendar error: {e}")
        
    print("\n--- earnings_dates ---")
    try:
        # This often returns a dataframe of historic and future dates
        ed = t.earnings_dates
        if ed is not None:
            print(ed.head())
        else:
            print("None")
    except Exception as e:
        print(f"Earnings Dates error: {e}")

if __name__ == "__main__":
    check_earnings("AAPL")
    check_earnings("TSLA")
