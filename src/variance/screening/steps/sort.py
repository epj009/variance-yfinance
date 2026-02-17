"""
Deduplication and Sorting Step
"""

from typing import Any


def sort_and_dedupe(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deduplicates by root symbol and sorts by signal quality."""

    # 1. Deduplicate by Root
    deduplicated: dict[str, dict[str, Any]] = {}
    for c in candidates:
        from variance.portfolio_parser import get_root_symbol

        symbol_val = c.get("symbol") or c.get("Symbol")
        if symbol_val is None:
            continue

        root = str(get_root_symbol(str(symbol_val)))

        # Priority: Keep shorter symbol name (usually the root)
        if root not in deduplicated or len(str(symbol_val)) < len(
            str(deduplicated[root].get("symbol") or deduplicated[root].get("Symbol"))
        ):
            deduplicated[root] = c

    final_list = list(deduplicated.values())

    # 2. Sort by Signal Quality
    def _signal_key(c: dict[str, Any]) -> tuple[float, float, int]:
        score_raw = c.get("score")
        score = float(score_raw) if score_raw is not None else 0.0

        # Check both cases for robustness
        vtm_raw = c.get("vrp_tactical_markup") or c.get("VRP_Tactical_Markup")
        vtm = float(vtm_raw) if vtm_raw is not None else -9.9

        proxy = c.get("proxy") or c.get("Proxy")
        quality = 1 if proxy else 0
        return (score, vtm, -quality)

    final_list.sort(key=_signal_key, reverse=True)
    return final_list
