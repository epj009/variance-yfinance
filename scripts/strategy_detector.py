"""
Strategy Detector Module

Handles strategy identification, clustering, and mapping for portfolio analysis.
Extracted from analyze_portfolio.py to improve maintainability.
"""

from collections import defaultdict
from typing import Dict, List, Optional, Any, TypedDict

# Import common utilities
try:
    from .portfolio_parser import parse_currency, parse_dte, get_root_symbol, is_stock_type
except ImportError:
    from portfolio_parser import parse_currency, parse_dte, get_root_symbol, is_stock_type


class StrategyCluster(TypedDict, total=False):
    """Type definition for a strategy cluster."""
    legs: List[Dict[str, Any]]
    strategy_name: str
    root_symbol: str


def identify_strategy(legs: List[Dict[str, Any]]) -> str:
    """
    Identify the option strategy based on a list of position legs.

    Analyzes the combination of Calls/Puts, Long/Short quantities, and strike prices
    to name the complex strategy (e.g., 'Iron Condor', 'Strangle', 'Covered Call').

    Args:
        legs: A list of normalized position legs belonging to one symbol group.

    Returns:
        The name of the strategy.
    """
    # This function now expects a list of legs that are already grouped as a potential strategy.
    # It will also be called with stock legs included for Covered strategies.

    if not legs: return "Empty"

    stock_legs = [l for l in legs if is_stock_type(l['Type'])]
    option_legs = [l for l in legs if not is_stock_type(l['Type'])]
    total_opt_legs = len(option_legs)

    if len(legs) == 1:
        leg = legs[0]
        if is_stock_type(leg['Type']): return "Stock"

        # Specific identification for single options
        qty = parse_currency(leg['Quantity'])
        otype = leg['Call/Put']
        if otype == 'Call':
            if qty > 0: return "Long Call"
            else: return "Short Call"
        elif otype == 'Put':
            if qty > 0: return "Long Put"
            else: return "Short Put"
        return "Single Option (Unknown Type)" # Fallback, should not happen if Call/Put is present

    # Metrics for option legs only - Initialization for single-pass aggregation
    expirations = set()
    stats = {
        'Call': {'long': {'count': 0, 'qty': 0.0, 'strikes': []}, 'short': {'count': 0, 'qty': 0.0, 'strikes': []}},
        'Put':  {'long': {'count': 0, 'qty': 0.0, 'strikes': []}, 'short': {'count': 0, 'qty': 0.0, 'strikes': []}}
    }

    # Single-Pass Aggregation
    for leg in option_legs:
        expirations.add(leg['Exp Date'])
        otype = leg['Call/Put']
        raw_qty = parse_currency(leg['Quantity'])
        qty_abs = abs(raw_qty)
        strike = parse_currency(leg['Strike Price'])

        side = 'long' if raw_qty > 0 else 'short'

        if otype in stats:
            bucket = stats[otype][side]
            bucket['count'] += 1
            bucket['qty'] += qty_abs
            bucket['strikes'].append(strike)

    is_multi_exp = len(expirations) > 1

    # Sort strikes
    for otype in stats:
        for side in stats[otype]:
            stats[otype][side]['strikes'].sort()

    # Unpack for compatibility with downstream logic
    long_calls = stats['Call']['long']['count']
    short_calls = stats['Call']['short']['count']
    long_call_qty = stats['Call']['long']['qty']
    short_call_qty = stats['Call']['short']['qty']
    long_call_strikes = stats['Call']['long']['strikes']
    short_call_strikes = stats['Call']['short']['strikes']

    long_puts = stats['Put']['long']['count']
    short_puts = stats['Put']['short']['count']
    long_put_qty = stats['Put']['long']['qty']
    short_put_qty = stats['Put']['short']['qty']
    long_put_strikes = stats['Put']['long']['strikes']
    short_put_strikes = stats['Put']['short']['strikes']

    # --- Stock-Option Combinations ---
    if stock_legs:
        if len(stock_legs) == 1:
            if total_opt_legs == 1:
                if short_calls == 1: return "Covered Call"
                if short_puts == 1: return "Covered Put" # This is usually a Cash-Secured Put, not a Covered Put
            if total_opt_legs == 2:
                if short_calls == 1 and short_puts == 1: return "Covered Strangle"
                if short_calls == 1 and long_puts == 1: return "Collar" # Assumes short call to offset long put
        # Add more complex stock-option combos here if needed
        return "Custom/Combo (Stock)" # Fallback for complex stock options

    # --- Pure Option Strategies ---
    if is_multi_exp:
        if total_opt_legs == 2:
            if short_calls == 1 and long_calls == 1:
                # Same strike = Calendar, Different strike = Diagonal
                if short_call_strikes and short_call_strikes[0] == long_call_strikes[0]:
                    return "Calendar Spread (Call)"
                return "Diagonal Spread (Call)"
            if short_puts == 1 and long_puts == 1:
                if short_put_strikes and short_put_strikes[0] == long_put_strikes[0]:
                    return "Calendar Spread (Put)"
                return "Diagonal Spread (Put)"
        if total_opt_legs == 4:
             return "Double Diagonal / Calendar"
        return "Custom/Combo (Multi-Exp)"

    if total_opt_legs == 4:
        # Standard 4-leg defined risk strategies
        if short_calls == 1 and long_calls == 1 and short_puts == 1 and long_puts == 1:
            if short_call_strikes and short_put_strikes and short_call_strikes[0] == short_put_strikes[0]:
                 return "Iron Butterfly" # Shorts share the same strike (ATM)
            return "Iron Condor" # Shorts are at different strikes (OTM)

    if total_opt_legs == 3:
        # 3-Leg strategies: Jade Lizard, Twisted Sister, Butterflies
        if short_puts >= 1 and short_calls >= 1 and long_calls >= 1 and long_puts == 0:
            return "Jade Lizard" # Short Put + Short Call Spread
        if short_calls >= 1 and short_puts >= 1 and long_puts >= 1 and long_calls == 0:
            return "Twisted Sister" # Short Call + Short Put Spread
        if long_calls == 2 and short_calls == 1 and long_call_qty == abs(short_call_qty): return "Long Call Butterfly"
        if long_puts == 2 and short_puts == 1 and long_put_qty == abs(short_put_qty): return "Long Put Butterfly"

    if total_opt_legs == 2:
        # Standard 2-leg strategies
        if short_calls >= 1 and short_puts >= 1: return "Strangle" # Short Call + Short Put
        if (long_calls >= 1 and short_calls >= 1):
            if long_call_qty != short_call_qty: return "Ratio Spread (Call)" # Uneven quantity
            return "Vertical Spread (Call)" # 1 Long, 1 Short
        if (long_puts >= 1 and short_puts >= 1):
            if long_put_qty != short_put_qty: return "Ratio Spread (Put)"
            return "Vertical Spread (Put)"

    return "Custom/Combo"


def cluster_strategies(positions: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
    """
    Group individual position legs into logical strategies (e.g., combining a short call and short put into a Strangle).

    Logic:
    1. Group all legs by Root Symbol.
    2. Within each Root:
       a. Group options by Expiration Date to find standard vertical/horizontal spreads.
       b. Match Stock legs with remaining Option legs to find Covered Calls/Collars.

    Args:
        positions: List of flat position rows.

    Returns:
        A list of lists, where each inner list is a group of legs forming a strategy.
    """
    by_root_all_legs = defaultdict(list)
    for row in positions:
        root = get_root_symbol(row['Symbol'])
        if root: # Ensure root is not empty
            by_root_all_legs[root].append(row)

    final_clusters = []

    for root, root_legs_original in by_root_all_legs.items():
        # Make a mutable copy for this root's legs
        root_legs = list(root_legs_original)

        stock_legs = [l for l in root_legs if is_stock_type(l['Type'])]
        option_legs = [l for l in root_legs if not is_stock_type(l['Type'])]

        # Used flags for options within this root to prevent double-counting legs
        option_used_flags = [False] * len(option_legs)
        stock_used_flags = [False] * len(stock_legs) # Keep track of used stocks

        # Phase 1: Identify pure option strategies (grouped by expiration)
        # Use a list of lists to build clusters within this root

        # Group options by expiration date to find standard spreads first
        by_exp_options = defaultdict(list)
        for i, leg in enumerate(option_legs):
            by_exp_options[leg['Exp Date']].append((i, leg))

        for exp, exp_legs_with_indices in by_exp_options.items():
            current_exp_options = [leg for idx, leg in exp_legs_with_indices if not option_used_flags[idx]] # Only consider unused options

            if len(current_exp_options) > 1: # Only look for strategies if > 1 option in this expiration
                # Temporarily create a sub-cluster
                temp_cluster = list(current_exp_options)
                strat_name = identify_strategy(temp_cluster)

                # If it's a known multi-leg strategy (not single option or custom/combo or stock)
                # We prioritize finding 'named' strategies over leaving them as loose legs
                if strat_name not in ["Single Option (Unknown Type)", "Custom/Combo", "Stock", "Empty", "Custom/Combo (Stock)"]:
                    final_clusters.append(temp_cluster)
                    # Mark all legs in this temp_cluster as used
                    for leg in temp_cluster:
                        # Find original index for this leg in option_legs and mark as used
                        original_idx = next((j for j, l in enumerate(option_legs) if l == leg), None)
                        if original_idx is not None:
                            option_used_flags[original_idx] = True

        # Phase 2: Handle stock-option combinations with remaining options
        unclustered_options_after_phase1 = [leg for i, leg in enumerate(option_legs) if not option_used_flags[i]]

        if stock_legs:
            # First, try 3-leg combinations: Covered Strangle, Collar

            # Covered Strangle (1 Stock + 1 Short Call + 1 Short Put)
            for s_idx, s_leg in enumerate(stock_legs):
                if stock_used_flags[s_idx]: continue

                temp_short_calls = [l for l in unclustered_options_after_phase1 if l['Call/Put'] == 'Call' and parse_currency(l['Quantity']) < 0]
                temp_short_puts = [l for l in unclustered_options_after_phase1 if l['Call/Put'] == 'Put' and parse_currency(l['Quantity']) < 0]

                if temp_short_calls and temp_short_puts:
                    # Greedily take the first available
                    current_combo = [s_leg, temp_short_calls[0], temp_short_puts[0]]
                    if identify_strategy(current_combo) == "Covered Strangle":
                        final_clusters.append(current_combo)
                        stock_used_flags[s_idx] = True
                        unclustered_options_after_phase1.remove(temp_short_calls[0])
                        unclustered_options_after_phase1.remove(temp_short_puts[0])
                        break # Break from stock loop, move to next

            # Collar (1 Stock + 1 Short Call + 1 Long Put)
            for s_idx, s_leg in enumerate(stock_legs):
                if stock_used_flags[s_idx]: continue

                temp_short_calls = [l for l in unclustered_options_after_phase1 if l['Call/Put'] == 'Call' and parse_currency(l['Quantity']) < 0]
                temp_long_puts = [l for l in unclustered_options_after_phase1 if l['Call/Put'] == 'Put' and parse_currency(l['Quantity']) > 0]

                if temp_short_calls and temp_long_puts:
                    current_combo = [s_leg, temp_short_calls[0], temp_long_puts[0]]
                    if identify_strategy(current_combo) == "Collar":
                        final_clusters.append(current_combo)
                        stock_used_flags[s_idx] = True
                        unclustered_options_after_phase1.remove(temp_short_calls[0])
                        unclustered_options_after_phase1.remove(temp_long_puts[0])
                        break

            # Now, try 2-leg combinations: Covered Call / Covered Put
            for s_idx, s_leg in enumerate(stock_legs):
                if stock_used_flags[s_idx]: continue

                for o_idx, o_leg in enumerate(unclustered_options_after_phase1):
                    current_combo = [s_leg, o_leg]
                    strat_name = identify_strategy(current_combo)
                    if strat_name in ["Covered Call", "Covered Put"]:
                        final_clusters.append(current_combo)
                        stock_used_flags[s_idx] = True
                        unclustered_options_after_phase1.remove(o_leg)
                        break # Move to next stock or stop trying for this stock

            # Add any remaining stock legs as single stock positions
            for s_idx, s_leg in enumerate(stock_legs):
                if not stock_used_flags[s_idx]:
                    final_clusters.append([s_leg])

            # Add any remaining (truly single) options
            for o_leg in unclustered_options_after_phase1:
                final_clusters.append([o_leg])

        else: # No stock legs, just add all option legs to final clusters
            for leg in unclustered_options_after_phase1: # Use the already processed ones
                final_clusters.append([leg])

    return final_clusters


def map_strategy_to_id(name: str, net_cost: float) -> Optional[str]:
    """
    Maps the output of identify_strategy() to the ID in strategies.json.

    Args:
        name: Strategy name from identify_strategy()
        net_cost: Net cost/credit of the position (negative = credit)

    Returns:
        Strategy ID matching strategies.json, or None if no mapping exists
    """
    name_lower = name.lower()

    # 1. Strangles & Straddles
    if "strangle" in name_lower:
        return "short_strangle"  # Variance assumes Short Strangle
    if "straddle" in name_lower:
        return "short_straddle"

    # 2. Iron Condors / Flies
    if "iron condor" in name_lower: return "iron_condor"
    if "iron butterfly" in name_lower: return "iron_fly"
    if "iron fly" in name_lower: return "iron_fly"

    # 3. Vertical Spreads (Directional)
    if "vertical spread" in name_lower:
        is_credit = net_cost < 0
        if "call" in name_lower:
            return "short_call_vertical_spread" if is_credit else "long_call_vertical_spread"
        if "put" in name_lower:
            return "short_put_vertical_spread" if is_credit else "long_put_vertical_spread"

    # 4. Calendars
    if "calendar spread" in name_lower:
        if "call" in name_lower: return "call_calendar_spread"
        if "put" in name_lower: return "put_calendar_spread"

    # 5. Naked Options (Short)
    if name_lower in ["short call"]: return "short_naked_call"
    if name_lower in ["short put"]: return "short_naked_put"

    # 6. Covered
    if "covered call" in name_lower: return "covered_call"
    if "covered put" in name_lower: return "covered_put"

    # 7. Exotics
    if "jade lizard" in name_lower: return "jade_lizard"
    if "ratio spread" in name_lower:
        if "call" in name_lower: return "call_front_ratio_spread"
        if "put" in name_lower: return "put_front_ratio_spread"
    if "butterfly" in name_lower:
        if "call" in name_lower: return "call_butterfly"
        if "put" in name_lower: return "put_butterfly"

    # 8. Double Diagonal
    if "double diagonal" in name_lower or "diagonal spread" in name_lower:
        return "double_diagonal" if net_cost < 0 else None

    # 9. Back Spread / Ratio Backspread
    if "back spread" in name_lower or ("ratio" in name_lower and "backspread" in name_lower):
        return "back_spread"

    return None
