"""
Condor Combination Step
"""

from typing import Any, Dict, List, Set


def combine_into_condors(
    call_verticals: List[List[Dict[str, Any]]],
    put_verticals: List[List[Dict[str, Any]]],
    used_indices: Set[int]
) -> List[List[Dict[str, Any]]]:
    """Combines matching verticals into Iron Condors."""
    clusters = []

    # We only combine credit spreads into Iron Condors here
    # (Simplified for now to match legacy behavior)

    # Legacy check: if we have both a call vertical and a put vertical
    # they should be combined if they aren't already part of a cluster.

    # For now, we return them as separate clusters to maintain
    # exact structural parity with the legacy detector output.
    # The actual 'Condor' naming happens in identify_strategy.

    clusters.extend(call_verticals)
    clusters.extend(put_verticals)

    return clusters
