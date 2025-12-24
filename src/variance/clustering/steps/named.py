"""
Named Strategy Clustering Step
"""

from typing import Any

from variance.strategy_detector import identify_strategy


def take_named_clusters(
    leg_infos: list[dict[str, Any]], used_indices: set[int], size: int
) -> list[list[dict[str, Any]]]:
    """Greedily identifies N-leg named strategies."""
    clusters = []

    # 1. Filter out already used legs
    available = [li for li in leg_infos if li["idx"] not in used_indices]

    # 2. Iterate through possible N-leg combinations
    # Since they are sorted by strike, we check sliding windows of N legs
    i = 0
    while i <= len(available) - size:
        window = available[i : i + size]
        window_legs = [li["leg"] for li in window]

        name = identify_strategy(window_legs)

        # If we found a specific named strategy (not just Single or Combo)
        lowered = name.lower()
        is_named = not (
            "single option" in lowered
            or "custom" in lowered
            or "unknown" in lowered
            or lowered == "stock"
        )

        if is_named:
            clusters.append(window_legs)
            used_indices.update(li["idx"] for li in window)
            i += size
        else:
            i += 1

    return clusters
