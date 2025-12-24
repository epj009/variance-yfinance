"""
Report Construction Step
"""

from datetime import datetime
from typing import Any, Dict, List


def build_report(
    candidates: List[Dict[str, Any]], 
    counters: Dict[str, int], 
    config: Any,
    rules: Dict[str, Any]
) -> Dict[str, Any]:
    """Constructs the final serialized report."""
    
    # 1. Final Summary Formatting
    structural_threshold = float(rules.get("vrp_structural_threshold", 0.85))
    if config.min_vrp_structural is not None:
        structural_threshold = float(config.min_vrp_structural)
        
    bias_note = f"VRP Structural (IV / HV) > {structural_threshold}"
    if config.min_vrp_structural is not None and config.min_vrp_structural <= 0:
        bias_note = "All symbols (no bias filter)"

    liq_mode = rules.get("liquidity_mode", "volume")
    if config.allow_illiquid:
        liquidity_note = "Illiquid included"
    else:
        liquidity_note = f"Illiquid filtered ({liq_mode} check)"

    summary = {
        "scanned_symbols_count": len(candidates) + sum(v for k, v in counters.items() if "skipped" in k),
        "candidates_count": len(candidates),
        "filter_note": f"{bias_note}; {liquidity_note}",
        **counters
    }

    return {
        "candidates": candidates,
        "summary": summary,
        "meta": {
            "scan_timestamp": datetime.now().isoformat(),
            "profile": getattr(config, "profile", "default")
        }
    }
