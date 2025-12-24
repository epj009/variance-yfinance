"""
Deduplication and Sorting Step
"""

from typing import Any, Dict, List


def sort_and_dedupe(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Deduplicates by root symbol and sorts by signal quality."""

    # 1. Deduplicate by Root
    deduplicated: Dict[str, Dict[str, Any]] = {}
    for c in candidates:
        from variance.portfolio_parser import get_root_symbol

        symbol_val = c.get("symbol") or c.get("Symbol")
        if symbol_val is None:
            continue

        root = str(get_root_symbol(str(symbol_val)))

        # Priority: Keep shorter symbol name (usually the root)
        if root not in deduplicated or len(str(symbol_val)) < len(str(deduplicated[root].get("symbol") or deduplicated[root].get("Symbol"))):
            deduplicated[root] = c

    final_list = list(deduplicated.values())

    # 2. Sort by Signal Quality
    def _signal_key(c):
        score = float(c.get("Score", 0.0))
        vtm = float(c.get("VRP_Tactical_Markup", -9.9))
        proxy = c.get("proxy") or c.get("Proxy")
        quality = 1 if proxy else 0
        return (score, vtm, -quality)

    final_list.sort(key=_signal_key, reverse=True)
    return final_list
