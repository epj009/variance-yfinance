"""
Leg Information Extraction Step
"""

from typing import TypedDict

from variance.models.position import Position


class LegInfo(TypedDict):
    idx: int
    leg: Position
    strike: float
    qty: int
    side: str
    type: str


def extract_leg_info(legs_with_idx: list[tuple[int, Position]]) -> list[LegInfo]:
    """Normalizes and sorts raw leg data for the pipeline."""
    leg_infos: list[LegInfo] = []
    for idx, leg in legs_with_idx:
        strike = float(leg.strike or 0.0)
        qty = int(float(leg.quantity))

        leg_infos.append(
            {
                "idx": idx,
                "leg": leg,
                "strike": strike,
                "qty": qty,
                "side": leg.call_put or "",
                "type": leg.asset_type,
            }
        )

    # Sort by strike price ascending for deterministic pairing
    leg_infos.sort(key=lambda x: float(x["strike"]))
    return leg_infos
