"""
Strangle Pairing Step
"""

from typing import Any


def pair_strangles(
    leg_infos: list[dict[str, Any]], used_indices: set[int]
) -> list[list[dict[str, Any]]]:
    """Pairs remaining short legs into Strangles/Straddles."""
    clusters = []

    available = [li for li in leg_infos if li["idx"] not in used_indices]
    short_calls = [li for li in available if li["side"] == "Call" and li["qty"] < 0]
    short_puts = [li for li in available if li["side"] == "Put" and li["qty"] < 0]

    # Pair calls with puts
    while short_calls and short_puts:
        c = short_calls.pop(0)
        p = short_puts.pop(0)

        clusters.append([c["leg"], p["leg"]])
        used_indices.add(c["idx"])
        used_indices.add(p["idx"])

    # Any remaining become single options
    remaining = [li for li in available if li["idx"] not in used_indices]
    for li in remaining:
        clusters.append([li["leg"]])
        used_indices.add(li["idx"])

    return clusters
