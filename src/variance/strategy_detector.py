"""
Strategy Detector Module

Handles strategy identification, clustering, and mapping for portfolio analysis.
Extracted from analyze_portfolio.py to improve maintainability.
"""

from collections import defaultdict
from datetime import datetime
from itertools import combinations
from typing import Any, Optional, TypedDict

# Import common utilities
from .portfolio_parser import get_root_symbol, is_stock_type, parse_currency, parse_dte


class StrategyCluster(TypedDict, total=False):
    """Type definition for a strategy cluster."""

    legs: list[dict[str, Any]]
    strategy_name: str
    root_symbol: str


def _leg_dte(leg: dict[str, Any]) -> int:
    dte = parse_dte(leg.get("DTE"))
    if dte > 0:
        return dte
    exp_str = leg.get("Exp Date")
    if not exp_str:
        return 0
    try:
        exp_date = datetime.strptime(exp_str, "%Y-%m-%d").date()
        return (exp_date - datetime.now().date()).days
    except ValueError:
        return 0


def _underlying_price(legs: list[dict[str, Any]]) -> float:
    if not legs:
        return 0.0
    return parse_currency(legs[0].get("Underlying Last Price", "0"))


def _aggregate_by_strike(legs: list[dict[str, Any]]) -> list[tuple[float, float]]:
    agg: dict[float, float] = {}
    for leg in legs:
        strike = parse_currency(leg.get("Strike Price", "0"))
        qty = parse_currency(leg.get("Quantity", "0"))
        agg[strike] = agg.get(strike, 0.0) + qty
    return sorted(agg.items(), key=lambda item: item[0])


def _is_pmcc_pair(
    long_leg: dict[str, Any], short_leg: dict[str, Any], underlying_price: float
) -> bool:
    long_dte = _leg_dte(long_leg)
    short_dte = _leg_dte(short_leg)
    if long_dte < 60 or long_dte < short_dte + 30:
        return False

    long_delta = parse_currency(long_leg.get("Delta", "0"))
    short_delta = parse_currency(short_leg.get("Delta", "0"))
    if long_delta != 0 and short_delta != 0:
        if long_delta < 0.60 or short_delta > 0.35 or short_delta <= 0:
            return False
    else:
        long_strike = parse_currency(long_leg.get("Strike Price", "0"))
        short_strike = parse_currency(short_leg.get("Strike Price", "0"))
        if underlying_price and not (long_strike < underlying_price < short_strike):
            return False

    return True


def _is_pmcp_pair(
    long_leg: dict[str, Any], short_leg: dict[str, Any], underlying_price: float
) -> bool:
    long_dte = _leg_dte(long_leg)
    short_dte = _leg_dte(short_leg)
    if long_dte < 60 or long_dte < short_dte + 30:
        return False

    long_delta = parse_currency(long_leg.get("Delta", "0"))
    short_delta = parse_currency(short_leg.get("Delta", "0"))
    if long_delta != 0 and short_delta != 0:
        if long_delta > -0.60 or short_delta < -0.35 or short_delta >= 0:
            return False
    else:
        long_strike = parse_currency(long_leg.get("Strike Price", "0"))
        short_strike = parse_currency(short_leg.get("Strike Price", "0"))
        if underlying_price and not (short_strike < underlying_price < long_strike):
            return False

    return True


def identify_strategy(legs: list[dict[str, Any]]) -> str:
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

    if not legs:
        return "Empty"

    stock_legs = [leg for leg in legs if is_stock_type(leg["Type"])]
    option_legs = [leg for leg in legs if not is_stock_type(leg["Type"])]
    total_opt_legs = len(option_legs)

    if len(legs) == 1:
        leg = legs[0]
        if is_stock_type(leg["Type"]):
            return "Stock"

        # Specific identification for single options
        qty = parse_currency(leg["Quantity"])
        otype = leg["Call/Put"]
        if otype == "Call":
            if qty > 0:
                return "Long Call"
            return "Short Call"
        if otype == "Put":
            if qty > 0:
                return "Long Put"
            return "Short Put"
        return "Single Option (Unknown Type)"

    expirations = {leg.get("Exp Date") for leg in option_legs}
    is_multi_exp = len(expirations) > 1
    underlying_price = _underlying_price(legs)

    call_legs = [leg for leg in option_legs if leg.get("Call/Put") == "Call"]
    put_legs = [leg for leg in option_legs if leg.get("Call/Put") == "Put"]

    def _side_legs(legs_list: list[dict[str, Any]], side: str) -> list[dict[str, Any]]:
        if side == "long":
            return [leg for leg in legs_list if parse_currency(leg.get("Quantity", "0")) > 0]
        return [leg for leg in legs_list if parse_currency(leg.get("Quantity", "0")) < 0]

    long_calls = _side_legs(call_legs, "long")
    short_calls = _side_legs(call_legs, "short")
    long_puts = _side_legs(put_legs, "long")
    short_puts = _side_legs(put_legs, "short")

    long_call_qty = sum(abs(parse_currency(leg.get("Quantity", "0"))) for leg in long_calls)
    short_call_qty = sum(abs(parse_currency(leg.get("Quantity", "0"))) for leg in short_calls)
    long_put_qty = sum(abs(parse_currency(leg.get("Quantity", "0"))) for leg in long_puts)
    short_put_qty = sum(abs(parse_currency(leg.get("Quantity", "0"))) for leg in short_puts)

    long_call_strikes = sorted(parse_currency(leg.get("Strike Price", "0")) for leg in long_calls)
    short_call_strikes = sorted(parse_currency(leg.get("Strike Price", "0")) for leg in short_calls)
    long_put_strikes = sorted(parse_currency(leg.get("Strike Price", "0")) for leg in long_puts)
    short_put_strikes = sorted(parse_currency(leg.get("Strike Price", "0")) for leg in short_puts)

    # --- Stock-Option Combinations ---
    if stock_legs:
        if len(stock_legs) == 1:
            if total_opt_legs == 1:
                if len(short_calls) == 1:
                    return "Covered Call"
                if len(short_puts) == 1:
                    return "Covered Put"
            if total_opt_legs == 2:
                if len(short_calls) == 1 and len(short_puts) == 1:
                    return "Covered Strangle"
                if len(short_calls) == 1 and len(long_puts) == 1:
                    return "Collar"
        # Add more complex stock-option combos here if needed
        return "Custom/Combo (Stock)"

    # --- Pure Option Strategies ---
    if is_multi_exp:
        if total_opt_legs == 2:
            if len(short_calls) == 1 and len(long_calls) == 1:
                short_leg = short_calls[0]
                long_leg = long_calls[0]
                if (
                    short_call_strikes
                    and long_call_strikes
                    and short_call_strikes[0] == long_call_strikes[0]
                ):
                    return "Calendar Spread (Call)"
                if _is_pmcc_pair(long_leg, short_leg, underlying_price):
                    return "Poor Man's Covered Call (Call Diagonal)"
                return "Diagonal Spread (Call)"
            if len(short_puts) == 1 and len(long_puts) == 1:
                short_leg = short_puts[0]
                long_leg = long_puts[0]
                if (
                    short_put_strikes
                    and long_put_strikes
                    and short_put_strikes[0] == long_put_strikes[0]
                ):
                    return "Calendar Spread (Put)"
                if _is_pmcp_pair(long_leg, short_leg, underlying_price):
                    return "Poor Man's Covered Put (Put Diagonal)"
                return "Diagonal Spread (Put)"
        if total_opt_legs == 4:
            return "Double Diagonal / Calendar"
        return "Custom/Combo (Multi-Exp)"

    def _butterfly_from_agg(agg: list[tuple[float, float]], option_type: str) -> Optional[str]:
        if len(agg) != 3:
            return None
        strikes = [s for s, _ in agg]
        qtys = [q for _, q in agg]
        abs_qtys = [abs(q) for q in qtys]
        if abs_qtys != [1.0, 2.0, 1.0]:
            return None
        if qtys[0] != qtys[2] or qtys[0] * qtys[1] >= 0:
            return None
        wing_left = abs(strikes[1] - strikes[0])
        wing_right = abs(strikes[2] - strikes[1])
        if wing_left == 0 or wing_right == 0:
            return None
        if wing_left == wing_right:
            return f"{option_type} Butterfly"
        return f"{option_type} Broken Wing Butterfly"

    def _broken_heart_from_agg(agg: list[tuple[float, float]], option_type: str) -> Optional[str]:
        if len(agg) != 4:
            return None
        qtys = [q for _, q in agg]
        abs_qtys = [abs(q) for q in qtys]
        if abs_qtys != [1.0, 1.0, 1.0, 1.0]:
            return None
        if qtys[0] != qtys[3] or qtys[1] != qtys[2] or qtys[0] * qtys[1] >= 0:
            return None
        return f"{option_type} Broken Heart Butterfly"

    def _ratio_from_agg(agg: list[tuple[float, float]], option_type: str) -> Optional[str]:
        if len(agg) != 2:
            return None
        (strike_low, qty_low), (strike_high, qty_high) = agg
        if option_type == "Call" and qty_low > 0 and qty_high < 0:
            if abs(qty_low) == 2 and abs(qty_high) == 1:
                return "Call ZEBRA"
            if abs(qty_low) == 1 and abs(qty_high) == 2:
                return "Call Front-Ratio Spread"
        if option_type == "Put" and qty_low < 0 and qty_high > 0:
            if abs(qty_high) == 2 and abs(qty_low) == 1:
                return "Put ZEBRA"
            if abs(qty_high) == 1 and abs(qty_low) == 2:
                return "Put Front-Ratio Spread"
        return None

    call_agg = _aggregate_by_strike(call_legs)
    put_agg = _aggregate_by_strike(put_legs)

    butterfly = _butterfly_from_agg(call_agg, "Call") or _butterfly_from_agg(put_agg, "Put")
    if butterfly:
        return butterfly

    broken_heart = _broken_heart_from_agg(call_agg, "Call") or _broken_heart_from_agg(
        put_agg, "Put"
    )
    if broken_heart:
        return broken_heart

    ratio = _ratio_from_agg(call_agg, "Call") or _ratio_from_agg(put_agg, "Put")
    if ratio:
        return ratio

    if total_opt_legs == 4:
        # Standard 4-leg defined risk strategies
        if (
            len(short_calls) == 1
            and len(long_calls) == 1
            and len(short_puts) == 1
            and len(long_puts) == 1
        ):
            if (
                short_call_strikes
                and short_put_strikes
                and short_call_strikes[0] == short_put_strikes[0]
            ):
                return "Iron Fly"
            call_width = (
                abs(long_call_strikes[0] - short_call_strikes[0])
                if long_call_strikes and short_call_strikes
                else 0
            )
            put_width = (
                abs(short_put_strikes[0] - long_put_strikes[0])
                if short_put_strikes and long_put_strikes
                else 0
            )
            if call_width and put_width and call_width != put_width:
                return "Dynamic Width Iron Condor"
            return "Iron Condor"

    if total_opt_legs == 3:
        # 3-Leg strategies: Jade Lizard, Reverse Jade, etc.
        if (
            len(short_puts) >= 1
            and len(short_calls) >= 1
            and len(long_calls) >= 1
            and len(long_puts) == 0
        ):
            short_put_strike = short_put_strikes[0] if short_put_strikes else 0
            if underlying_price and short_put_strike >= underlying_price:
                return "Big Lizard"
            return "Jade Lizard"
        if (
            len(short_calls) >= 1
            and len(short_puts) >= 1
            and len(long_puts) >= 1
            and len(long_calls) == 0
        ):
            short_call_strike = short_call_strikes[0] if short_call_strikes else 0
            if underlying_price and short_call_strike <= underlying_price:
                return "Reverse Big Lizard"
            return "Reverse Jade Lizard"

    if total_opt_legs == 2:
        # Standard 2-leg strategies
        if (
            len(short_calls) >= 1
            and len(short_puts) >= 1
            and len(long_calls) == 0
            and len(long_puts) == 0
        ):
            if (
                short_call_strikes
                and short_put_strikes
                and short_call_strikes[0] == short_put_strikes[0]
            ):
                return "Short Straddle"
            return "Short Strangle"
        if len(long_calls) >= 1 and len(short_calls) >= 1:
            if long_call_qty != short_call_qty:
                return "Ratio Spread (Call)"
            return "Vertical Spread (Call)"
        if len(long_puts) >= 1 and len(short_puts) >= 1:
            if long_put_qty != short_put_qty:
                return "Ratio Spread (Put)"
            return "Vertical Spread (Put)"

    return "Custom/Combo"


def cluster_strategies(positions: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
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
        root = get_root_symbol(row["Symbol"])
        if root:  # Ensure root is not empty
            by_root_all_legs[root].append(row)

    final_clusters = []

    for _root, root_legs_original in by_root_all_legs.items():
        # Make a mutable copy for this root's legs
        root_legs = list(root_legs_original)

        stock_legs = [leg for leg in root_legs if is_stock_type(leg["Type"])]
        option_legs = [leg for leg in root_legs if not is_stock_type(leg["Type"])]

        # Used flags for options within this root to prevent double-counting legs
        option_used_flags = [False] * len(option_legs)
        stock_used_flags = [False] * len(stock_legs)  # Keep track of used stocks

        # Phase 1: Identify pure option strategies (grouped by expiration)
        # Group options by expiration date to find standard spreads first
        by_exp_options = defaultdict(list)
        for i, leg in enumerate(option_legs):
            by_exp_options[leg["Exp Date"]].append((i, leg))

        for _exp, exp_legs_with_indices in by_exp_options.items():
            current_exp_options = [
                (idx, leg) for idx, leg in exp_legs_with_indices if not option_used_flags[idx]
            ]

            if len(current_exp_options) > 1:
                exp_clusters, used_indices = _cluster_expiration_options(current_exp_options)
                final_clusters.extend(exp_clusters)
                for used_idx in used_indices:
                    option_used_flags[used_idx] = True

        # Phase 1b: Cross-expiration clustering (calendars/diagonals/PMCC/PMCP)
        remaining_with_indices = [
            (i, leg) for i, leg in enumerate(option_legs) if not option_used_flags[i]
        ]
        if remaining_with_indices:
            cross_clusters, cross_used = _cluster_cross_expiration_options(remaining_with_indices)
            final_clusters.extend(cross_clusters)
            for used_idx in cross_used:
                option_used_flags[used_idx] = True

        # Phase 2: Handle stock-option combinations with remaining options
        unclustered_options_after_phase1 = [
            leg for i, leg in enumerate(option_legs) if not option_used_flags[i]
        ]

        if stock_legs:
            # First, try 3-leg combinations: Covered Strangle, Collar

            # Covered Strangle (1 Stock + 1 Short Call + 1 Short Put)
            for s_idx, s_leg in enumerate(stock_legs):
                if stock_used_flags[s_idx]:
                    continue

                temp_short_calls = [
                    leg
                    for leg in unclustered_options_after_phase1
                    if leg["Call/Put"] == "Call" and parse_currency(leg["Quantity"]) < 0
                ]
                temp_short_puts = [
                    leg
                    for leg in unclustered_options_after_phase1
                    if leg["Call/Put"] == "Put" and parse_currency(leg["Quantity"]) < 0
                ]

                if temp_short_calls and temp_short_puts:
                    # Greedily take the first available
                    current_combo = [s_leg, temp_short_calls[0], temp_short_puts[0]]
                    if identify_strategy(current_combo) == "Covered Strangle":
                        final_clusters.append(current_combo)
                        stock_used_flags[s_idx] = True
                        unclustered_options_after_phase1.remove(temp_short_calls[0])
                        unclustered_options_after_phase1.remove(temp_short_puts[0])
                        break  # Break from stock loop, move to next

            # Collar (1 Stock + 1 Short Call + 1 Long Put)
            for s_idx, s_leg in enumerate(stock_legs):
                if stock_used_flags[s_idx]:
                    continue

                temp_short_calls = [
                    leg
                    for leg in unclustered_options_after_phase1
                    if leg["Call/Put"] == "Call" and parse_currency(leg["Quantity"]) < 0
                ]
                temp_long_puts = [
                    leg
                    for leg in unclustered_options_after_phase1
                    if leg["Call/Put"] == "Put" and parse_currency(leg["Quantity"]) > 0
                ]

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
                if stock_used_flags[s_idx]:
                    continue

                for leg in unclustered_options_after_phase1:
                    current_combo = [s_leg, leg]
                    strat_name = identify_strategy(current_combo)
                    if strat_name in ["Covered Call", "Covered Put"]:
                        final_clusters.append(current_combo)
                        stock_used_flags[s_idx] = True
                        unclustered_options_after_phase1.remove(leg)
                        break  # Move to next stock or stop trying for this stock

            # Add any remaining stock legs as single stock positions
            for s_idx, s_leg in enumerate(stock_legs):
                if not stock_used_flags[s_idx]:
                    final_clusters.append([s_leg])

            # Add any remaining (truly single) options
            for o_leg in unclustered_options_after_phase1:
                final_clusters.append([o_leg])

        else:  # No stock legs, just add all option legs to final clusters
            for leg in unclustered_options_after_phase1:  # Use the already processed ones
                final_clusters.append([leg])

    return final_clusters


def _cluster_expiration_options(
    exp_legs_with_indices: list[tuple[int, dict[str, Any]]],
) -> tuple[list[list[dict[str, Any]]], set[int]]:
    """
    Cluster options within a single expiration to avoid merging distinct strategies.
    """
    clusters: list[list[dict[str, Any]]] = []
    used_indices: set[int] = set()

    # Split by Open Date to prevent merging different trades opened at different times.
    # If Open Date is missing, we treat it as a single 'Unknown' bucket to allow
    # greedy matching, but we must ensure we don't merge distinct strategies.
    by_open_date: dict[str, list[tuple[int, dict[str, Any]]]] = defaultdict(list)
    for idx, leg in exp_legs_with_indices:
        # If date is missing, use a unique-ish key per leg to avoid forced merging
        # but ONLY if we want to be strict. Actually, for greedy matching to work
        # (e.g. matching a loose call and put into a strangle), they SHOULD be in the same bucket.
        # The bug is likely that we are TOO greedy.
        key = (leg.get("Open Date") or "UNKNOWN").strip()
        by_open_date[key].append((idx, leg))

    for _, legs_with_idx in by_open_date.items():
        group_clusters, group_used = _cluster_same_open_date(legs_with_idx)
        clusters.extend(group_clusters)
        used_indices.update(group_used)

    return clusters, used_indices


def _cluster_cross_expiration_options(
    legs_with_indices: list[tuple[int, dict[str, Any]]],
) -> tuple[list[list[dict[str, Any]]], set[int]]:
    """
    Cluster multi-expiration option pairs (calendars/diagonals/PMCC/PMCP).
    """
    clusters: list[list[dict[str, Any]]] = []
    used_indices: set[int] = set()

    excluded_names = {
        "Single Option (Unknown Type)",
        "Custom/Combo",
        "Custom/Combo (Stock)",
        "Custom/Combo (Multi-Exp)",
        "Stock",
        "Empty",
    }

    by_open_date: dict[str, list[tuple[int, dict[str, Any]]]] = defaultdict(list)
    for idx, leg in legs_with_indices:
        key = (leg.get("Open Date") or "").strip()
        by_open_date[key].append((idx, leg))

    for _, group in by_open_date.items():
        candidates = []
        for (idx_a, leg_a), (idx_b, leg_b) in combinations(group, 2):
            if idx_a in used_indices or idx_b in used_indices:
                continue
            if leg_a.get("Call/Put") != leg_b.get("Call/Put"):
                continue
            if leg_a.get("Exp Date") == leg_b.get("Exp Date"):
                continue
            qty_a = parse_currency(leg_a.get("Quantity", "0"))
            qty_b = parse_currency(leg_b.get("Quantity", "0"))
            if qty_a == 0 or qty_b == 0 or qty_a * qty_b > 0:
                continue

            name = identify_strategy([leg_a, leg_b])
            if name in excluded_names:
                continue
            name_lower = name.lower()
            priority = 3
            if "calendar spread" in name_lower:
                priority = 0
            elif "poor man's covered" in name_lower or "poor mans covered" in name_lower:
                priority = 1
            elif "diagonal spread" in name_lower:
                priority = 2

            dte_diff = abs(_leg_dte(leg_a) - _leg_dte(leg_b))
            candidates.append((priority, dte_diff, idx_a, idx_b, [leg_a, leg_b]))

        candidates.sort(key=lambda item: (item[0], item[1]))
        for _, _, idx_a, idx_b, candidate_legs in candidates:
            if idx_a in used_indices or idx_b in used_indices:
                continue
            clusters.append(candidate_legs)
            used_indices.add(idx_a)
            used_indices.add(idx_b)

    return clusters, used_indices


def _cluster_same_open_date(legs_with_idx: list[tuple[int, dict[str, Any]]]) -> tuple[list[list[dict[str, Any]]], set[int]]:
    """
    Groups options into logical clusters using the Clustering Pipeline.
    """
    from .clustering.pipeline import ClusteringPipeline
    
    pipeline = ClusteringPipeline()
    clusters, used_indices = pipeline.cluster(legs_with_idx)
    
    return clusters, used_indices


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
    if "dynamic width iron condor" in name_lower:
        return "dynamic_width_iron_condor"
    if "iron condor" in name_lower:
        return "iron_condor"
    if "iron butterfly" in name_lower or "iron fly" in name_lower:
        return "iron_fly"

    # 3. Vertical Spreads (Directional)
    if "vertical spread" in name_lower:
        is_credit = net_cost < 0
        if "call" in name_lower:
            return "short_call_vertical_spread" if is_credit else "long_call_vertical_spread"
        if "put" in name_lower:
            return "short_put_vertical_spread" if is_credit else "long_put_vertical_spread"

    # 4. Calendars / Diagonals
    if "calendar spread" in name_lower:
        if "call" in name_lower:
            return "call_calendar_spread"
        if "put" in name_lower:
            return "put_calendar_spread"
    if "poor man's covered call" in name_lower or "poor mans covered call" in name_lower:
        return "poor_mans_covered_call"
    if "poor man's covered put" in name_lower or "poor mans covered put" in name_lower:
        return "poor_mans_covered_put"

    # 5. Naked Options (Short)
    if name_lower in ["short call"]:
        return "short_naked_call"
    if name_lower in ["short put"]:
        return "short_naked_put"

    # 6. Covered
    if "covered call" in name_lower:
        return "covered_call"
    if "covered put" in name_lower:
        return "covered_put"

    # 7. ZEBRA
    if "call zebra" in name_lower:
        return "call_zebra"
    if "put zebra" in name_lower:
        return "put_zebra"

    # 8. Exotics
    if "reverse big lizard" in name_lower:
        return "reverse_big_lizard"
    if "big lizard" in name_lower:
        return "big_lizard"
    if "reverse jade lizard" in name_lower or "twisted sister" in name_lower:
        return "reverse_jade_lizard"
    if "jade lizard" in name_lower:
        return "jade_lizard"
    if "front-ratio" in name_lower or "front ratio" in name_lower or "ratio spread" in name_lower:
        if "call" in name_lower:
            return "call_front_ratio_spread"
        if "put" in name_lower:
            return "put_front_ratio_spread"
    if "broken wing butterfly" in name_lower:
        if "call" in name_lower:
            return "call_broken_wing_butterfly"
        if "put" in name_lower:
            return "put_broken_wing_butterfly"
    if "broken heart butterfly" in name_lower:
        if "call" in name_lower:
            return "call_broken_heart_butterfly"
        if "put" in name_lower:
            return "put_broken_heart_butterfly"
    if "butterfly" in name_lower:
        if "call" in name_lower:
            return "call_butterfly"
        if "put" in name_lower:
            return "put_butterfly"

    # 9. Double Diagonal
    if "double diagonal" in name_lower or "diagonal spread" in name_lower:
        return "double_diagonal" if net_cost < 0 else None

    # 10. Back Spread / Ratio Backspread
    if "back spread" in name_lower or ("ratio" in name_lower and "backspread" in name_lower):
        return "back_spread"

    return None
