import yfinance as yf

symbols = ["GLD", "CL=F", "IBIT", "SPY"]

print("--- Starting Diagnostic ---")

for sym in symbols:
    print(f"\nTesting {sym}...")
    t = yf.Ticker(sym)
    
    # Test 1: Fast Info (The preferred way)
    try:
        price = t.fast_info.last_price
        print(f"  [Fast Info] Price: {price}")
    except Exception as e:
        print(f"  [Fast Info] Failed: {e}")

    # Test 2: History (The robust backup)
    try:
        hist = t.history(period="1d")
        if not hist.empty:
            print(f"  [History] Close: {hist['Close'].iloc[-1]}")
        else:
            print(f"  [History] Empty DataFrame")
    except Exception as e:
        print(f"  [History] Failed: {e}")

    # Test 3: The "Info" dictionary (The likely culprit)
    try:
        # This triggers the 'quoteSummary' request that often 404s
        info = t.info 
        print(f"  [Info] Price: {info.get('regularMarketPrice')}")
    except Exception as e:
        print(f"  [Info] Failed: {e}")
