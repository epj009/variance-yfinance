"""
Vertical Spread Pairing Step
"""

from typing import Any, Dict, List, Set, Tuple


def pair_verticals(
    leg_infos: List[Dict[str, Any]], 
    used_indices: Set[int]
) -> Tuple[List[List[Dict[str, Any]]], List[List[Dict[str, Any]]]]:
    """Identifies and pairs remaining legs into vertical spreads."""
    call_verticals = []
    put_verticals = []
    
    available = [li for li in leg_infos if li["idx"] not in used_indices]
    
    # Separate available legs into sides and types
    short_calls = [li for li in available if li["side"] == "Call" and li["qty"] < 0]
    long_calls = [li for li in available if li["side"] == "Call" and li["qty"] > 0]
    short_puts = [li for li in available if li["side"] == "Put" and li["qty"] < 0]
    long_puts = [li for li in available if li["side"] == "Put" and li["qty"] > 0]

    # Helper to pair by strike proximity
    def _pair(shorts, longs):
        paired = []
        s_idx = 0
        while s_idx < len(shorts):
            s_li = shorts[s_idx]
            # Find closest long by strike
            best_l = None
            best_dist = float('inf')
            best_l_idx = -1
            
            for i, l_li in enumerate(longs):
                if l_li["idx"] in used_indices: continue
                dist = abs(s_li["strike"] - l_li["strike"])
                if dist < best_dist:
                    best_dist = dist
                    best_l = l_li
                    best_l_idx = i
            
            if best_l:
                paired.append([s_li["leg"], best_l["leg"]])
                used_indices.add(s_li["idx"])
                used_indices.add(best_l["idx"])
                longs.pop(best_l_idx) # Remove used long
            s_idx += 1
        return paired

    call_verticals = _pair(short_calls, long_calls)
    put_verticals = _pair(short_puts, long_puts)
    
    return call_verticals, put_verticals
