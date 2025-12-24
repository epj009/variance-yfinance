"""
Leg Information Extraction Step
"""

from typing import Any, Dict, List, Tuple

from variance.portfolio_parser import parse_currency


def extract_leg_info(legs_with_idx: List[Tuple[int, Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """Normalizes and sorts raw leg data for the pipeline."""
    leg_infos = []
    for idx, leg in legs_with_idx:
        strike = float(parse_currency(leg.get("Strike Price", "0")))
        qty = int(float(parse_currency(leg.get("Quantity", "0"))))

        leg_infos.append({
            "idx": idx,
            "leg": leg,
            "strike": strike,
            "qty": qty,
            "side": leg.get("Call/Put", ""),
            "type": leg.get("Type", "")
        })

    # Sort by strike price ascending for deterministic pairing
    leg_infos.sort(key=lambda x: x["strike"])
    return leg_infos
