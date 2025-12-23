import os
import sys

import yfinance as yf

# Add scripts to path for common utils
sys.path.append(os.getcwd())
sys.path.append(os.path.join(os.getcwd(), "scripts"))

from scripts.get_market_data import calculate_hv, get_market_data, map_symbol

TEST_FUTURES = ["/6C", "/6A", "/6E", "/ZT", "/ZN", "/NQ"]

CURRENT_PROXIES = {
    "/6C": {"type": "etf", "iv_symbol": "FXC", "hv_symbol": "FXC"},
    "/6A": {"type": "etf", "iv_symbol": "FXA", "hv_symbol": "FXA"},
    "/6E": {"type": "etf", "iv_symbol": "FXE", "hv_symbol": "FXE"},
    "/ZT": {"type": "etf", "iv_symbol": "SHY", "hv_symbol": "SHY"},
    "/ZN": {"type": "etf", "iv_symbol": "IEF", "hv_symbol": "IEF"},
    "/NQ": {"type": "vol_index", "iv_symbol": "^VXN", "hv_symbol": "NQ=F"},
}

PROPOSED_PROXIES = {
    "/6C": {"type": "vol_index", "iv_symbol": "^EVZ", "hv_symbol": "6C=F"},
    "/6A": {"type": "vol_index", "iv_symbol": "^EVZ", "hv_symbol": "6A=F"},
    "/6E": {"type": "vol_index", "iv_symbol": "^EVZ", "hv_symbol": "6E=F"},
    "/ZT": {"type": "etf", "iv_symbol": "IEF", "hv_symbol": "ZT=F"},
    "/ZN": {"type": "etf", "iv_symbol": "IEF", "hv_symbol": "IEF"},
    "/NQ": {"type": "vol_index", "iv_symbol": "^VIX", "hv_symbol": "NQ=F"},
}


def get_proxy_vol(proxy_config, raw_symbol):
    ptype = proxy_config.get("type")
    iv = None
    note = ""

    try:
        if ptype == "vol_index":
            iv_sym = proxy_config["iv_symbol"]
            iv_t = yf.Ticker(iv_sym)
            iv_hist = iv_t.history(period="1mo")
            if not iv_hist.empty:
                iv = iv_hist["Close"].iloc[-1]
                note = f"IV:{iv_sym}"
        elif ptype == "etf":
            etf_sym = proxy_config.get("iv_symbol")
            # Fetch using standard get_market_data which handles chains/liquidity
            # Use a fresh fetch by clearing cache effectively or just trusting current state
            data = get_market_data([etf_sym]).get(etf_sym, {})
            iv = data.get("iv")
            note = f"IV:{etf_sym}"
    except Exception as e:
        note = f"ERR:{str(e)}"

    return iv, note


def run_bake_off():
    print("--- PROXY BAKE-OFF RESEARCH ---")
    print(
        f"{'SYMBOL':<8} | {'CURRENT PROXY':<15} | {'CURRENT VRP':<12} | {'PROPOSED PROXY':<15} | {'PROPOSED VRP':<12} | {'DIVERGENCE'}"
    )
    print("-" * 100)

    for sym in TEST_FUTURES:
        # Get REAL HV for the idiosyncratic symbol
        yf_sym = map_symbol(sym)
        ticker = yf.Ticker(yf_sym)
        hv_data = calculate_hv(ticker, yf_sym)
        hv = hv_data.get("hv252") if hv_data else None

        if not hv:
            print(f"{sym:<8} | ERROR: No HV for actual future.")
            continue

        # 1. Current Calc
        curr_cfg = CURRENT_PROXIES[sym]
        iv_curr, note_curr = get_proxy_vol(curr_cfg, sym)
        vrp_curr = iv_curr / hv if iv_curr and hv else None

        # 2. Proposed Calc
        prop_cfg = PROPOSED_PROXIES[sym]
        iv_prop, note_prop = get_proxy_vol(prop_cfg, sym)
        vrp_prop = iv_prop / hv if iv_prop and hv else None

        # Display
        curr_str = f"{vrp_curr:.2f} ({note_curr})" if vrp_curr else f"None ({note_curr})"
        prop_str = f"{vrp_prop:.2f} ({note_prop})" if vrp_prop else f"None ({note_prop})"

        delta = ""
        if vrp_curr and vrp_prop:
            d_val = vrp_prop - vrp_curr
            delta = f"{d_val:+.2f}"
            if abs(d_val) > 0.5:
                delta += " ⚠️"
        elif not vrp_curr and vrp_prop:
            delta = "✅ RESTORED"

        print(
            f"{sym:<8} | {curr_cfg['iv_symbol']:<15} | {curr_str:<12} | {prop_cfg['iv_symbol']:<15} | {prop_str:<12} | {delta}"
        )


if __name__ == "__main__":
    # Clear cache to get fresh proxy data
    if os.path.exists(".market_cache.db"):
        os.remove(".market_cache.db")
    run_bake_off()
