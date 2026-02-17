import csv
import math
import os
import sys
from typing import Any

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from variance.config_loader import load_config_bundle
from variance.market_data.service import MarketDataFactory


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        val = float(value)
        if math.isnan(val):
            return default
        return val
    except (TypeError, ValueError):
        return default


def run_bake_off() -> None:
    print("🔬 VARIANCE RESEARCH: IV Scaling Bake-off")
    print("Goal: Prove that Log-Normalization creates valid VRP signals from decimal noise.")
    print("-" * 70)

    config_bundle = load_config_bundle()
    watchlist_path = config_bundle["system_config"].get(
        "watchlist_path", "watchlists/default-watchlist.csv"
    )

    symbols: list[str] = []
    with open(watchlist_path) as f:
        reader = csv.reader(f)
        for row in reader:
            if row and row[0] != "Symbol":
                symbols.append(row[0])

    print(f"Sampling {len(symbols)} symbols...")
    provider = MarketDataFactory.get_provider()
    # Fetch a small batch for speed
    data = provider.get_market_data(symbols[:50])

    print(
        f"{'Symbol':<8} | {'HV':<6} | {'IV Raw':<8} | {'VRP Raw':<8} | {'VRP Fixed':<8} | {'Status'}"
    )
    print("-" * 75)

    for sym, metrics in data.items():
        if "error" in metrics:
            continue

        hv = _safe_float(metrics.get("hv252", 0))
        iv_raw = _safe_float(metrics.get("iv", 0))  # This is already normalized in production,
        # let's simulate the raw value for demo

        # Simulation: Assume the provider sent a decimal if it's currently a whole number
        # (to show the comparison) or use the real normalized status.
        warning = metrics.get("warning")

        if warning == "iv_scale_corrected":
            # Recover the original decimal
            real_raw = iv_raw / 100.0
            vrp_raw = real_raw / hv if hv > 0 else 0.0
            vrp_fixed = iv_raw / hv if hv > 0 else 0.0

            status = "✅ FIXED"
            print(
                f"{sym:<8} | {hv:<6.1f} | {real_raw:<8.3f} | {vrp_raw:<8.2f} | {vrp_fixed:<8.2f} | {status}"
            )
        else:
            vrp = iv_raw / hv if hv > 0 else 0.0
            print(f"{sym:<8} | {hv:<6.1f} | {iv_raw:<8.1f} | {vrp:<8.2f} | {vrp:<8.2f} | ---")


if __name__ == "__main__":
    run_bake_off()
