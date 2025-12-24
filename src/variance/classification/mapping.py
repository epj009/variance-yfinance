"""
Strategy Name to ID Mapping

Declarative mapping table for normalizing strategy names into configuration IDs.
"""

from typing import Dict, List, Optional, Callable, Tuple

# Direct mappings (no conditions required)
DIRECT_MAP: Dict[str, str] = {
    "short strangle": "short_strangle",
    "strangle": "short_strangle",
    "short straddle": "short_straddle",
    "straddle": "short_straddle",
    "iron condor": "iron_condor",
    "dynamic width iron condor": "dynamic_width_iron_condor",
    "iron fly": "iron_fly",
    "iron butterfly": "iron_fly",
    "covered call": "covered_call",
    "covered put": "covered_put",
    "short call": "short_naked_call",
    "short put": "short_naked_put",
    "jade lizard": "jade_lizard",
    "big lizard": "big_lizard",
    "reverse jade lizard": "reverse_jade_lizard",
    "twisted sister": "reverse_jade_lizard",
    "reverse big lizard": "reverse_big_lizard",
    "call zebra": "call_zebra",
    "put zebra": "put_zebra",
    "butterfly (call)": "butterfly_call",
    "butterfly (put)": "butterfly_put",
    "call butterfly": "butterfly_call",
    "put butterfly": "butterfly_put",
    "call calendar spread": "call_calendar_spread",
    "put calendar spread": "put_calendar_spread",
    "calendar spread (call)": "call_calendar_spread",
    "calendar spread (put)": "put_calendar_spread",
}

# Conditional rules (mapping depends on net_cost/premium side)
# List of (keyword, condition_fn, strategy_id)
CONDITIONAL_RULES: List[Tuple[str, Callable[[str, float], bool], str]] = [
    ("vertical spread", lambda n, c: "call" in n and c < 0, "short_call_vertical_spread"),
    ("vertical spread", lambda n, c: "call" in n and c >= 0, "long_call_vertical_spread"),
    ("vertical spread", lambda n, c: "put" in n and c < 0, "short_put_vertical_spread"),
    ("vertical spread", lambda n, c: "put" in n and c >= 0, "long_put_vertical_spread"),
    ("ratio spread", lambda n, c: "call" in n, "ratio_spread_call"),
    ("ratio spread", lambda n, c: "put" in n, "ratio_spread_put"),
    ("diagonal spread", lambda n, c: "call" in n, "call_diagonal_spread"),
    ("diagonal spread", lambda n, c: "put" in n, "put_diagonal_spread"),
]


def map_strategy_to_id(name: str, net_cost: float) -> Optional[str]:
    """
    Normalizes a human-readable strategy name into a stable configuration ID.
    """
    n_lower = name.lower()
    
    # 1. Direct Lookup
    if n_lower in DIRECT_MAP:
        return DIRECT_MAP[n_lower]
        
    # 2. Rule-based Lookup
    for keyword, condition, strat_id in CONDITIONAL_RULES:
        if keyword in n_lower and condition(n_lower, net_cost):
            return strat_id
            
    # 3. Fallbacks
    if "stock" in n_lower:
        return "stock"
        
    return None
