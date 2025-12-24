"""
Named Strategy Clustering Step
"""

from typing import Any, Dict, List, Set

from variance.strategy_detector import identify_strategy


def take_named_clusters(
    leg_infos: List[Dict[str, Any]],
    used_indices: Set[int],
    size: int
) -> List[List[Dict[str, Any]]]:
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
        is_named = name not in ["Single Option", "Custom Combo", "Unknown Strategy"]

        if is_named:
            clusters.append(window_legs)
            used_indices.update(li["idx"] for li in window)
            i += size
        else:
            i += 1

    return clusters
