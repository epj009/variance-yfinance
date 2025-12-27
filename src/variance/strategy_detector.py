"""
Strategy Detector Module

Handles strategy identification, clustering, and mapping for portfolio analysis.
Extracted from analyze_portfolio.py to improve maintainability.
"""

import json
from collections import defaultdict
from datetime import datetime
from functools import lru_cache
from itertools import combinations
from pathlib import Path
from typing import Any, Optional, TypedDict

from .models.position import Position

# Import common utilities
from .portfolio_parser import get_root_symbol, is_stock_type


class StrategyCluster(TypedDict, total=False):
    """Type definition for a strategy cluster."""

    legs: list[Position]
    strategy_name: str
    root_symbol: str


def _ensure_position(leg: Position) -> Position:
    if not isinstance(leg, Position):
        raise TypeError(
            "Strategy detection expects Position objects. "
            "Use PortfolioParser.parse_positions or Position.from_row."
        )
    return leg


def _ensure_positions(legs: list[Position]) -> list[Position]:
    for idx, leg in enumerate(legs):
        if not isinstance(leg, Position):
            raise TypeError(
                f"Strategy detection expects Position objects; got {type(leg).__name__} "
                f"at index {idx}. Use PortfolioParser.parse_positions or Position.from_row."
            )
    return list(legs)


def _leg_dte(leg: Position) -> int:
    position = _ensure_position(leg)
    if position.dte > 0:
        return position.dte
    exp_str = position.exp_date
    if not exp_str:
        return 0
    try:
        exp_date = datetime.strptime(exp_str, "%Y-%m-%d").date()
        return (exp_date - datetime.now().date()).days
    except ValueError:
        return 0


from .classification.registry import ClassifierChain

# Module-level chain (singleton)
_CLASSIFIER_CHAIN: Optional[ClassifierChain] = None


def _get_chain() -> ClassifierChain:
    global _CLASSIFIER_CHAIN
    if _CLASSIFIER_CHAIN is None:
        _CLASSIFIER_CHAIN = ClassifierChain()
    return _CLASSIFIER_CHAIN


def identify_strategy(legs: list[Position]) -> str:
    """
    Identify the option strategy based on a list of position legs.
    """
    positions = _ensure_positions(legs)
    return _get_chain().classify(positions)


def cluster_strategies(positions: list[Position]) -> list[list[Position]]:
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
    positions = _ensure_positions(positions)
    by_root_all_legs = _group_legs_by_root(positions)

    final_clusters: list[list[Position]] = []
    for _root, root_legs_original in by_root_all_legs.items():
        final_clusters.extend(_cluster_root_legs(list(root_legs_original)))

    return final_clusters


def _group_legs_by_root(positions: list[Position]) -> dict[str, list[Position]]:
    by_root_all_legs: dict[str, list[Position]] = defaultdict(list)
    for leg in positions:
        root = leg.root_symbol or get_root_symbol(leg.symbol)
        if root:  # Ensure root is not empty
            by_root_all_legs[root].append(leg)
    return by_root_all_legs


def _cluster_root_legs(root_legs: list[Position]) -> list[list[Position]]:
    stock_legs = [leg for leg in root_legs if is_stock_type(leg.asset_type)]
    option_legs = [leg for leg in root_legs if not is_stock_type(leg.asset_type)]

    option_used_flags = [False] * len(option_legs)
    clusters: list[list[Position]] = []

    clusters.extend(_cluster_options_by_expiration(option_legs, option_used_flags))
    clusters.extend(_cluster_cross_expiration(option_legs, option_used_flags))

    unclustered_options = [leg for i, leg in enumerate(option_legs) if not option_used_flags[i]]

    if stock_legs:
        clusters.extend(_cluster_with_stocks(stock_legs, unclustered_options))
    else:
        clusters.extend([[leg] for leg in unclustered_options])

    return clusters


def _cluster_options_by_expiration(
    option_legs: list[Position], option_used_flags: list[bool]
) -> list[list[Position]]:
    clusters: list[list[Position]] = []
    by_exp_options = defaultdict(list)
    for i, leg in enumerate(option_legs):
        by_exp_options[leg.exp_date].append((i, leg))

    for _exp, exp_legs_with_indices in by_exp_options.items():
        current_exp_options = [
            (idx, leg) for idx, leg in exp_legs_with_indices if not option_used_flags[idx]
        ]

        if len(current_exp_options) > 1:
            exp_clusters, used_indices = _cluster_expiration_options(current_exp_options)
            clusters.extend(exp_clusters)
            for used_idx in used_indices:
                option_used_flags[used_idx] = True

    return clusters


def _cluster_cross_expiration(
    option_legs: list[Position], option_used_flags: list[bool]
) -> list[list[Position]]:
    clusters: list[list[Position]] = []
    remaining_with_indices = [
        (i, leg) for i, leg in enumerate(option_legs) if not option_used_flags[i]
    ]
    if remaining_with_indices:
        cross_clusters, cross_used = _cluster_cross_expiration_options(remaining_with_indices)
        clusters.extend(cross_clusters)
        for used_idx in cross_used:
            option_used_flags[used_idx] = True
    return clusters


def _cluster_with_stocks(
    stock_legs: list[Position], unclustered_options: list[Position]
) -> list[list[Position]]:
    clusters: list[list[Position]] = []
    stock_used_flags = [False] * len(stock_legs)

    _apply_covered_strangle(stock_legs, unclustered_options, stock_used_flags, clusters)
    _apply_collar(stock_legs, unclustered_options, stock_used_flags, clusters)
    _apply_covered_single(stock_legs, unclustered_options, stock_used_flags, clusters)

    for s_idx, s_leg in enumerate(stock_legs):
        if not stock_used_flags[s_idx]:
            clusters.append([s_leg])

    for o_leg in unclustered_options:
        clusters.append([o_leg])

    return clusters


def _apply_covered_strangle(
    stock_legs: list[Position],
    unclustered_options: list[Position],
    stock_used_flags: list[bool],
    clusters: list[list[Position]],
) -> None:
    for s_idx, s_leg in enumerate(stock_legs):
        if stock_used_flags[s_idx]:
            continue

        temp_short_calls = [
            leg for leg in unclustered_options if (leg.call_put == "Call" and leg.quantity < 0)
        ]
        temp_short_puts = [
            leg for leg in unclustered_options if (leg.call_put == "Put" and leg.quantity < 0)
        ]

        if temp_short_calls and temp_short_puts:
            current_combo = [s_leg, temp_short_calls[0], temp_short_puts[0]]
            if identify_strategy(current_combo) == "Covered Strangle":
                clusters.append(current_combo)
                stock_used_flags[s_idx] = True
                unclustered_options.remove(temp_short_calls[0])
                unclustered_options.remove(temp_short_puts[0])
                break


def _apply_collar(
    stock_legs: list[Position],
    unclustered_options: list[Position],
    stock_used_flags: list[bool],
    clusters: list[list[Position]],
) -> None:
    for s_idx, s_leg in enumerate(stock_legs):
        if stock_used_flags[s_idx]:
            continue

        temp_short_calls = [
            leg for leg in unclustered_options if (leg.call_put == "Call" and leg.quantity < 0)
        ]
        temp_long_puts = [
            leg for leg in unclustered_options if (leg.call_put == "Put" and leg.quantity > 0)
        ]

        if temp_short_calls and temp_long_puts:
            current_combo = [s_leg, temp_short_calls[0], temp_long_puts[0]]
            if identify_strategy(current_combo) == "Collar":
                clusters.append(current_combo)
                stock_used_flags[s_idx] = True
                unclustered_options.remove(temp_short_calls[0])
                unclustered_options.remove(temp_long_puts[0])
                break


def _apply_covered_single(
    stock_legs: list[Position],
    unclustered_options: list[Position],
    stock_used_flags: list[bool],
    clusters: list[list[Position]],
) -> None:
    for s_idx, s_leg in enumerate(stock_legs):
        if stock_used_flags[s_idx]:
            continue

        for leg in list(unclustered_options):
            current_combo = [s_leg, leg]
            strat_name = identify_strategy(current_combo)
            if strat_name in ["Covered Call", "Covered Put"]:
                clusters.append(current_combo)
                stock_used_flags[s_idx] = True
                unclustered_options.remove(leg)
                break


def _cluster_expiration_options(
    exp_legs_with_indices: list[tuple[int, Position]],
) -> tuple[list[list[Position]], set[int]]:
    """
    Cluster options within a single expiration to avoid merging distinct strategies.
    """
    clusters: list[list[Position]] = []
    used_indices: set[int] = set()

    # Split by Open Date to prevent merging different trades opened at different times.
    # If Open Date is missing, we treat it as a single 'Unknown' bucket to allow
    # greedy matching, but we must ensure we don't merge distinct strategies.
    by_open_date: dict[str, list[tuple[int, Position]]] = defaultdict(list)
    for idx, leg in exp_legs_with_indices:
        # If date is missing, use a unique-ish key per leg to avoid forced merging
        # but ONLY if we want to be strict. Actually, for greedy matching to work
        # (e.g. matching a loose call and put into a strangle), they SHOULD be in the same bucket.
        # The bug is likely that we are TOO greedy.
        key = (leg.open_date or "UNKNOWN").strip()
        by_open_date[key].append((idx, leg))

    for _, legs_with_idx in by_open_date.items():
        group_clusters, group_used = _cluster_same_open_date(legs_with_idx)
        clusters.extend(group_clusters)
        used_indices.update(group_used)

    return clusters, used_indices


def _cluster_cross_expiration_options(
    legs_with_indices: list[tuple[int, Position]],
) -> tuple[list[list[Position]], set[int]]:
    """
    Cluster multi-expiration option pairs (calendars/diagonals/PMCC/PMCP).
    """
    clusters: list[list[Position]] = []
    used_indices: set[int] = set()

    excluded_names = {
        "Single Option (Unknown Type)",
        "Custom/Combo",
        "Custom/Combo (Stock)",
        "Custom/Combo (Multi-Exp)",
        "Stock",
        "Empty",
    }

    by_open_date: dict[str, list[tuple[int, Position]]] = defaultdict(list)
    for idx, leg in legs_with_indices:
        key = (leg.open_date or "").strip()
        by_open_date[key].append((idx, leg))

    for _, group in by_open_date.items():
        candidates = []
        for (idx_a, leg_a), (idx_b, leg_b) in combinations(group, 2):
            if idx_a in used_indices or idx_b in used_indices:
                continue
            if leg_a.call_put != leg_b.call_put:
                continue
            if leg_a.exp_date == leg_b.exp_date:
                continue
            qty_a = leg_a.quantity
            qty_b = leg_b.quantity
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


def _cluster_same_open_date(
    legs_with_idx: list[tuple[int, Position]],
) -> tuple[list[list[Position]], set[int]]:
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
    is_credit = net_cost < 0

    for rule in _load_strategy_mappings():
        rule_type = str(rule.get("type", "contains"))
        side = rule.get("side")
        if side and side not in name_lower:
            continue

        match = False
        if rule_type == "exact":
            match = name_lower == str(rule.get("pattern", ""))
        elif rule_type == "contains":
            match = str(rule.get("pattern", "")) in name_lower
        elif rule_type == "contains_any":
            patterns = rule.get("patterns", [])
            match = any(str(pat) in name_lower for pat in patterns)
        elif rule_type == "contains_all":
            patterns = rule.get("patterns", [])
            match = all(str(pat) in name_lower for pat in patterns)

        if not match:
            continue

        if rule.get("credit_only"):
            return rule.get("id") if is_credit else None
        if rule.get("debit_only"):
            return rule.get("id") if not is_credit else None

        credit_id = rule.get("credit_id")
        debit_id = rule.get("debit_id")
        if credit_id or debit_id:
            return credit_id if is_credit else debit_id

        return rule.get("id")

    return None


@lru_cache(maxsize=1)
def _load_strategy_mappings() -> list[dict[str, Any]]:
    root = Path(__file__).resolve().parents[2]
    path = root / "config" / "strategy_mappings.json"
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, list):
        raise ValueError("strategy_mappings.json must be a list of rule objects.")
    return [rule for rule in data if isinstance(rule, dict)]
